import hashlib
import hmac
import json
import os
import posixpath
import re
import secrets
import sqlite3
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

DIRETORIO_BASE = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(DIRETORIO_BASE, "loja.db")
ARQUIVO_ESQUEMA = os.path.join(DIRETORIO_BASE, "schema.sql")
ARQUIVO_DADOS = os.path.join(DIRETORIO_BASE, "DI.sql")

ITERACOES_SENHA = 200_000
TAMANHO_MINIMO_USUARIO = 3
TAMANHO_MAXIMO_USUARIO = 50
TAMANHO_MINIMO_SENHA = 8
TAMANHO_MAXIMO_SENHA = 128
DURACAO_SESSAO = 8 * 60 * 60
TAMANHO_MAXIMO_REQUISICAO = 1_000_000
TAMANHO_MAXIMO_NOME_PRODUTO = 100
TAMANHO_MAXIMO_DESCRICAO = 300
TAMANHO_MAXIMO_CATEGORIA = 50
PRECO_MAXIMO_CENTAVOS = 100_000_000
ESTOQUE_MAXIMO = 1_000_000

MAX_TENTATIVAS_LOGIN = 5
JANELA_LOGIN = 5 * 60

ARQUIVOS_PUBLICOS = {"/", "/index.html", "/style.css", "/script.js"}
PASTA_IMAGENS = "/Imagens/"
LOGIN_INVALIDO = "Usuário ou senha incorretos."
POLITICA_CONTEUDO = (
    "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; "
    "base-uri 'self'; form-action 'self'"
)

SESSOES_WEB = {}
SESSOES_WEB_LOCK = threading.Lock()
TENTATIVAS_LOGIN = {}
TENTATIVAS_LOGIN_LOCK = threading.Lock()


def ler_senha(prompt="Senha: "):
    if not sys.stdin.isatty():
        import getpass

        return getpass.getpass(prompt)

    sys.stdout.write(prompt)
    sys.stdout.flush()
    caracteres = []

    if os.name == "nt":
        import msvcrt

        while True:
            caractere = msvcrt.getwch()
            if caractere in ("\r", "\n"):
                print()
                break
            if caractere == "\x03":
                raise KeyboardInterrupt
            if caractere in ("\x00", "\xe0"):
                msvcrt.getwch()
                continue
            if caractere in ("\b", "\x7f"):
                if caracteres:
                    caracteres.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            else:
                caracteres.append(caractere)
                sys.stdout.write("*")
                sys.stdout.flush()
    else:
        import termios
        import tty

        entrada = sys.stdin.fileno()
        configuracao_original = termios.tcgetattr(entrada)
        try:
            tty.setraw(entrada)
            while True:
                caractere = sys.stdin.read(1)
                if caractere in ("\r", "\n", "\x04", ""):
                    break
                if caractere == "\x03":
                    raise KeyboardInterrupt
                if caractere in ("\x7f", "\b"):
                    if caracteres:
                        caracteres.pop()
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                else:
                    caracteres.append(caractere)
                    sys.stdout.write("*")
                    sys.stdout.flush()
        finally:
            termios.tcsetattr(entrada, termios.TCSADRAIN, configuracao_original)
            print()

    return "".join(caracteres)


def ler_arquivo(caminho):
    with open(caminho, encoding="utf-8") as arquivo:
        return arquivo.read()


def verificar_arquivos_sql():
    if not os.path.exists(ARQUIVO_ESQUEMA):
        print("Arquivo schema.sql não encontrado. Ele precisa estar na mesma pasta do app.py.")
        sys.exit(1)
    if not os.path.exists(ARQUIVO_DADOS):
        print("Aviso: DI.sql não encontrado. A loja abrirá sem produtos de exemplo.")


def conectar_banco():
    conexao = sqlite3.connect(DB_NAME, timeout=10)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


@contextmanager
def banco():
    conexao = conectar_banco()
    try:
        yield conexao
    finally:
        conexao.close()


def colunas_das_tabelas(conexao):
    tabelas = [
        linha[0]
        for linha in conexao.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    return {
        tabela: {coluna[1] for coluna in conexao.execute(f"PRAGMA table_info({tabela})")}
        for tabela in tabelas
    }


def esquema_esperado():
    memoria = sqlite3.connect(":memory:")
    try:
        memoria.executescript(ler_arquivo(ARQUIVO_ESQUEMA))
        return colunas_das_tabelas(memoria)
    finally:
        memoria.close()


def banco_compativel():
    if not os.path.exists(DB_NAME):
        return True
    try:
        conexao = sqlite3.connect(DB_NAME)
        try:
            existentes = colunas_das_tabelas(conexao)
        finally:
            conexao.close()
    except sqlite3.DatabaseError:
        return False
    esperado = esquema_esperado()
    return all(esperado.get(tabela) == colunas for tabela, colunas in existentes.items())


def apagar_banco():
    for sufixo in ("", "-wal", "-shm", "-journal"):
        caminho = DB_NAME + sufixo
        if os.path.exists(caminho):
            os.remove(caminho)


def guardar_backup_banco():
    destino = f"{DB_NAME}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
    os.replace(DB_NAME, destino)
    for sufixo in ("-wal", "-shm", "-journal"):
        if os.path.exists(DB_NAME + sufixo):
            os.remove(DB_NAME + sufixo)
    return destino


def preparar_banco(zerar=False):
    if zerar:
        apagar_banco()
        print("Banco de dados zerado.")
    elif not banco_compativel():
        destino = guardar_backup_banco()
        print(f"Banco antigo e incompatível. Uma cópia foi guardada em {os.path.basename(destino)} e um novo banco será criado.")


def achar_linha_com_erro(conexao, sql):
    cabecalho = re.search(r"INSERT\s+INTO\s+produtos\s*\([^)]*\)\s*VALUES", sql, re.IGNORECASE)
    if not cabecalho:
        return None
    deslocamento = sql[: cabecalho.end()].count("\n")
    for numero, linha in enumerate(sql[cabecalho.end():].splitlines(), start=deslocamento + 1):
        texto = linha.strip().rstrip(",;").strip()
        if not texto.startswith("("):
            continue
        conexao.execute("SAVEPOINT teste_dados")
        try:
            conexao.execute(f"{cabecalho.group(0)} {texto}")
        except sqlite3.Error:
            return numero, linha.strip()
        finally:
            conexao.execute("ROLLBACK TO teste_dados")
            conexao.execute("RELEASE teste_dados")
    return None


def mensagem_erro_dados(conexao, sql, erro):
    partes = [
        f"Erro ao carregar o DI.sql: {erro}",
        f"Arquivo lido pelo programa: {ARQUIVO_DADOS}",
        "(se você editou outro DI.sql, ou não salvou com Ctrl+S, a mudança não vale)",
    ]
    try:
        achado = achar_linha_com_erro(conexao, sql)
    except sqlite3.Error:
        achado = None
    if achado:
        partes.append(f"Linha {achado[0]} do DI.sql: {achado[1]}")
    partes.append(
        "Confira: (1) o preço antigo precisa ser MAIOR que o preço atual, os dois em centavos "
        "(14990 = R$ 149,90) ou NULL; (2) a ordem dos valores é categoria, nome, descrição, "
        "imagem, preço, preço antigo, estoque; (3) a categoria existe na lista do topo do arquivo."
    )
    return "\n".join(partes)


def inicializar_banco(conexao):
    conexao.executescript(ler_arquivo(ARQUIVO_ESQUEMA))
    total = conexao.execute("SELECT COUNT(*) FROM produtos").fetchone()[0]
    if total == 0 and os.path.exists(ARQUIVO_DADOS):
        sql = ler_arquivo(ARQUIVO_DADOS)
        try:
            conexao.executescript(sql)
        except sqlite3.Error as erro:
            raise SystemExit(mensagem_erro_dados(conexao, sql, erro)) from None
    conexao.commit()


def validar_credenciais(nome_usuario, senha):
    if len(nome_usuario) < TAMANHO_MINIMO_USUARIO:
        raise ValueError(
            f"O nome de usuário precisa ter pelo menos {TAMANHO_MINIMO_USUARIO} caracteres."
        )
    if len(nome_usuario) > TAMANHO_MAXIMO_USUARIO:
        raise ValueError(
            f"O nome de usuário pode ter no máximo {TAMANHO_MAXIMO_USUARIO} caracteres."
        )
    if len(senha) < TAMANHO_MINIMO_SENHA:
        raise ValueError(
            f"A senha precisa ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres."
        )
    if len(senha) > TAMANHO_MAXIMO_SENHA:
        raise ValueError(
            f"A senha pode ter no máximo {TAMANHO_MAXIMO_SENHA} caracteres."
        )


def gerar_hash_senha(senha, sal=None):
    if sal is None:
        sal = secrets.token_bytes(16)
    hash_bytes = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, ITERACOES_SENHA)
    return sal.hex(), hash_bytes.hex()


def criar_usuario(conexao, nome_usuario, senha, papel="cliente"):
    nome_usuario = nome_usuario.strip()
    if papel not in ("admin", "cliente"):
        raise ValueError("Tipo de usuário inválido.")
    validar_credenciais(nome_usuario, senha)

    sal, hash_senha = gerar_hash_senha(senha)
    cursor = conexao.execute(
        "INSERT INTO usuarios (nome_usuario, sal, hash_senha, papel) VALUES (?, ?, ?, ?)",
        (nome_usuario, sal, hash_senha, papel),
    )
    conexao.commit()
    return {"id": cursor.lastrowid, "nome_usuario": nome_usuario, "papel": papel}


def criar_administrador_inicial(conexao):
    total = conexao.execute(
        "SELECT COUNT(*) AS total FROM usuarios WHERE papel = 'admin'"
    ).fetchone()["total"]
    if total:
        return

    nome_env = os.environ.get("TRACKFLOW_ADMIN_USER", "").strip()
    senha_env = os.environ.get("TRACKFLOW_ADMIN_SENHA", "")
    if nome_env and senha_env:
        try:
            criar_usuario(conexao, nome_env, senha_env, papel="admin")
            print("Administrador criado a partir das variáveis de ambiente.")
            return
        except (ValueError, sqlite3.IntegrityError) as erro:
            print(f"Não foi possível usar as variáveis de ambiente: {erro}")

    print("\n=== Configuração inicial da loja ===")
    print("Crie a conta de administrador. A senha aparecerá como asteriscos (*).")
    while True:
        nome = input("Nome de usuário do administrador: ").strip()
        senha = ler_senha("Crie uma senha (mínimo 8 caracteres): ")
        confirmacao = ler_senha("Digite a senha novamente: ")
        if senha != confirmacao:
            print("As senhas não correspondem. Tente novamente.\n")
            continue
        try:
            criar_usuario(conexao, nome, senha, papel="admin")
            print("Administrador criado com sucesso.\n")
            return
        except ValueError as erro:
            print(f"Não foi possível criar a conta: {erro}\n")
        except sqlite3.IntegrityError:
            print("Não foi possível criar a conta: esse nome de usuário já existe.\n")


def autenticar(conexao, nome_usuario, senha):
    usuario = conexao.execute(
        "SELECT * FROM usuarios WHERE nome_usuario = ?", (nome_usuario.strip(),)
    ).fetchone()

    if usuario is None:
        gerar_hash_senha(senha, b"\x00" * 16)
        return None

    _, hash_calculado = gerar_hash_senha(senha, bytes.fromhex(usuario["sal"]))
    if hmac.compare_digest(hash_calculado, usuario["hash_senha"]):
        return usuario
    return None


def formatar_preco(centavos):
    reais, centavos_restantes = divmod(int(centavos), 100)
    reais_formatado = f"{reais:,}".replace(",", ".")
    return f"R$ {reais_formatado},{centavos_restantes:02d}"


def converter_preco_para_centavos(valor_texto):
    texto = str(valor_texto).strip().replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", texto):
        texto = texto.replace(".", "")
    try:
        valor = Decimal(texto)
    except InvalidOperation as erro:
        raise ValueError("Preço inválido. Exemplo: 50,00") from erro
    if not valor.is_finite() or valor <= 0:
        raise ValueError("O preço precisa ser maior que zero.")
    valor = valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    centavos = int(valor * 100)
    if centavos <= 0:
        raise ValueError("O preço precisa ser de pelo menos R$ 0,01.")
    if centavos > PRECO_MAXIMO_CENTAVOS:
        raise ValueError("Preço acima do limite permitido.")
    return centavos


def converter_inteiro(valor, campo):
    if isinstance(valor, bool) or (isinstance(valor, float) and not valor.is_integer()):
        raise ValueError(f"{campo} precisa ser um número inteiro.")
    try:
        return int(valor)
    except (TypeError, ValueError) as erro:
        raise ValueError(f"{campo} precisa ser um número inteiro.") from erro


def buscar_produtos(conexao):
    linhas = conexao.execute(
        "SELECT produtos.id, produtos.nome, produtos.descricao, produtos.imagem, "
        "produtos.preco_centavos, produtos.preco_antigo_centavos, produtos.estoque, "
        "produtos.categoria_id, categorias.nome AS categoria "
        "FROM produtos JOIN categorias ON categorias.id = produtos.categoria_id "
        "ORDER BY categorias.id, produtos.id"
    ).fetchall()
    return [dict(linha) for linha in linhas]


def buscar_categorias(conexao):
    linhas = conexao.execute("SELECT id, nome FROM categorias ORDER BY id").fetchall()
    return [dict(linha) for linha in linhas]


def cadastrar_categoria(conexao, usuario, nome):
    exigir_admin(usuario)
    nome = str(nome).strip()
    if not nome:
        raise ValueError("Informe o nome da categoria.")
    if len(nome) > TAMANHO_MAXIMO_CATEGORIA:
        raise ValueError(f"O nome da categoria pode ter no máximo {TAMANHO_MAXIMO_CATEGORIA} caracteres.")
    try:
        conexao.execute("INSERT INTO categorias (nome) VALUES (?)", (nome,))
    except sqlite3.IntegrityError as erro:
        raise ValueError("Já existe uma categoria com esse nome.") from erro
    conexao.commit()


def exigir_admin(usuario):
    if usuario["papel"] != "admin":
        raise PermissionError("Somente o administrador pode fazer isso.")


def cadastrar_produto(conexao, usuario, nome, preco_texto, estoque, descricao="", imagem="",
                      preco_antigo_texto="", categoria_id=None):
    exigir_admin(usuario)

    nome = str(nome).strip()
    descricao = str(descricao).strip()
    imagem = str(imagem).strip()
    if not nome:
        raise ValueError("Informe o nome do produto.")
    if len(nome) > TAMANHO_MAXIMO_NOME_PRODUTO:
        raise ValueError(f"O nome pode ter no máximo {TAMANHO_MAXIMO_NOME_PRODUTO} caracteres.")
    if len(descricao) > TAMANHO_MAXIMO_DESCRICAO:
        raise ValueError(f"A descrição pode ter no máximo {TAMANHO_MAXIMO_DESCRICAO} caracteres.")
    if imagem and (not imagem.startswith("Imagens/") or ".." in imagem):
        raise ValueError("A imagem precisa estar na pasta Imagens/ (ex.: Imagens/produto.png).")

    preco_centavos = converter_preco_para_centavos(preco_texto)
    preco_antigo = None
    if str(preco_antigo_texto).strip():
        preco_antigo = converter_preco_para_centavos(preco_antigo_texto)
        if preco_antigo <= preco_centavos:
            raise ValueError("O preço antigo precisa ser maior que o preço atual.")

    estoque = converter_inteiro(estoque, "O estoque")
    if estoque < 0 or estoque > ESTOQUE_MAXIMO:
        raise ValueError(f"O estoque precisa estar entre 0 e {ESTOQUE_MAXIMO}.")

    categoria_id = converter_inteiro(categoria_id, "A categoria")
    if conexao.execute("SELECT 1 FROM categorias WHERE id = ?", (categoria_id,)).fetchone() is None:
        raise ValueError("Categoria não encontrada.")

    try:
        conexao.execute(
            "INSERT INTO produtos "
            "(categoria_id, nome, descricao, imagem, preco_centavos, preco_antigo_centavos, estoque) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (categoria_id, nome, descricao, imagem, preco_centavos, preco_antigo, estoque),
        )
    except sqlite3.IntegrityError as erro:
        raise ValueError("Já existe um produto com esse nome.") from erro
    conexao.commit()


def atualizar_estoque(conexao, usuario, produto_id, estoque):
    exigir_admin(usuario)
    produto_id = converter_inteiro(produto_id, "O ID do produto")
    estoque = converter_inteiro(estoque, "O estoque")
    if estoque < 0 or estoque > ESTOQUE_MAXIMO:
        raise ValueError(f"O estoque precisa estar entre 0 e {ESTOQUE_MAXIMO}.")
    cursor = conexao.execute("UPDATE produtos SET estoque = ? WHERE id = ?", (estoque, produto_id))
    if cursor.rowcount != 1:
        raise ValueError("Produto não encontrado.")
    conexao.commit()


def processar_pedido(conexao, usuario_id, itens):
    quantidades = {}
    for produto_id, quantidade in itens:
        if (
            isinstance(produto_id, bool)
            or isinstance(quantidade, bool)
            or not isinstance(produto_id, int)
            or not isinstance(quantidade, int)
        ):
            raise ValueError("Os IDs e as quantidades precisam ser números inteiros.")
        if produto_id <= 0 or quantidade <= 0:
            raise ValueError("O ID e a quantidade precisam ser maiores que zero.")
        quantidades[produto_id] = quantidades.get(produto_id, 0) + quantidade

    if not quantidades:
        raise ValueError("Adicione pelo menos um produto ao pedido.")

    try:
        conexao.execute("BEGIN IMMEDIATE")

        usuario = conexao.execute(
            "SELECT id, papel FROM usuarios WHERE id = ?", (usuario_id,)
        ).fetchone()
        if usuario is None:
            raise ValueError("Usuário não encontrado.")
        if usuario["papel"] != "cliente":
            raise PermissionError("Apenas contas de cliente podem finalizar pedidos.")

        itens_validados = []
        total_centavos = 0
        for produto_id, quantidade in quantidades.items():
            produto = conexao.execute(
                "SELECT id, nome, preco_centavos, estoque FROM produtos WHERE id = ?",
                (produto_id,),
            ).fetchone()
            if produto is None:
                raise ValueError(f"Produto de ID {produto_id} não encontrado.")
            if produto["estoque"] < quantidade:
                raise ValueError(
                    f"Estoque insuficiente para '{produto['nome']}'. "
                    f"Disponível: {produto['estoque']}."
                )
            preco = produto["preco_centavos"]
            total_centavos += preco * quantidade
            itens_validados.append((produto, quantidade, preco))

        cursor = conexao.execute(
            "INSERT INTO pedidos (usuario_id, total_centavos) VALUES (?, ?)",
            (usuario_id, total_centavos),
        )
        pedido_id = cursor.lastrowid

        for produto, quantidade, preco in itens_validados:
            conexao.execute(
                "INSERT INTO itens_pedido "
                "(pedido_id, produto_id, quantidade, preco_unitario_centavos) "
                "VALUES (?, ?, ?, ?)",
                (pedido_id, produto["id"], quantidade, preco),
            )
            atualizacao = conexao.execute(
                "UPDATE produtos SET estoque = estoque - ? WHERE id = ? AND estoque >= ?",
                (quantidade, produto["id"], quantidade),
            )
            if atualizacao.rowcount != 1:
                raise ValueError(
                    f"Não foi possível reservar o estoque de '{produto['nome']}'."
                )

        conexao.commit()
        return pedido_id, total_centavos
    except Exception:
        conexao.rollback()
        raise


def buscar_pedidos(conexao, usuario_id):
    linhas = conexao.execute(
        "SELECT pedido_id, data_criacao, total_centavos, produto_id, produto_nome, "
        "quantidade, preco_unitario_centavos "
        "FROM vw_pedidos_detalhados WHERE usuario_id = ? "
        "ORDER BY pedido_id DESC, produto_id",
        (usuario_id,),
    ).fetchall()

    pedidos = {}
    for linha in linhas:
        pedido = pedidos.setdefault(
            linha["pedido_id"],
            {
                "id": linha["pedido_id"],
                "data": linha["data_criacao"].replace(" ", "T") + "Z",
                "total_centavos": linha["total_centavos"],
                "total": formatar_preco(linha["total_centavos"]),
                "itens": [],
            },
        )
        pedido["itens"].append({
            "produto_id": linha["produto_id"],
            "nome": linha["produto_nome"],
            "quantidade": linha["quantidade"],
            "preco_unitario_centavos": linha["preco_unitario_centavos"],
        })
    return list(pedidos.values())


def listar_produtos(conexao):
    produtos = buscar_produtos(conexao)
    if not produtos:
        print("\nNenhum produto cadastrado.\n")
        return

    print("\n=== Produtos disponíveis ===")
    for produto in produtos:
        print(
            f"ID: {produto['id']} | [{produto['categoria']}] {produto['nome']} | "
            f"{formatar_preco(produto['preco_centavos'])} | "
            f"Estoque: {produto['estoque']}"
        )
    print()


def listar_meus_pedidos(conexao, usuario_id):
    pedidos = buscar_pedidos(conexao, usuario_id)
    if not pedidos:
        print("\nVocê ainda não fez pedidos.\n")
        return

    print("\n=== Seus pedidos ===")
    for pedido in pedidos:
        resumo = ", ".join(f"{i['nome']} (x{i['quantidade']})" for i in pedido["itens"])
        print(
            f"Pedido #{pedido['id']} | {pedido['data'][:16].replace('T', ' ')} UTC | "
            f"{pedido['total']}\n  Itens: {resumo}"
        )
    print()


def cadastrar_produto_pelo_menu(conexao, usuario):
    print("\n=== Cadastro de produto ===")
    nome = input("Nome do produto: ")
    descricao = input("Descrição (opcional): ")
    print("Categorias:")
    for categoria in buscar_categorias(conexao):
        print(f"  {categoria['id']} - {categoria['nome']}")
    categoria_id = input("ID da categoria: ")
    imagem = input("Caminho da imagem, ex.: Imagens/produto.png (opcional): ")
    preco = input("Preço (ex.: 50,00): ")
    preco_antigo = input("Preço antigo, se estiver em oferta (opcional): ")
    estoque = input("Quantidade em estoque: ")
    cadastrar_produto(conexao, usuario, nome, preco, estoque, descricao, imagem, preco_antigo, categoria_id)
    print("Produto cadastrado com sucesso!\n")


def comprar_pelo_menu(conexao, usuario):
    listar_produtos(conexao)
    print("Digite os itens como ID:quantidade, separados por vírgula.")
    print("Exemplo: 1:2, 3:1 (dois do produto 1 e um do produto 3)")
    texto = input("Itens do pedido: ").strip()
    itens = []
    try:
        for parte in texto.split(","):
            produto_id, quantidade = parte.strip().split(":")
            itens.append((int(produto_id), int(quantidade)))
        pedido_id, total = processar_pedido(conexao, usuario["id"], itens)
        print(f"Pedido #{pedido_id} finalizado! Total: {formatar_preco(total)}\n")
    except (ValueError, PermissionError) as erro:
        print(f"Não foi possível finalizar o pedido: {erro}\n")


def painel_usuario(conexao, usuario):
    while True:
        print(f"\nOlá, {usuario['nome_usuario']}! Perfil: {usuario['papel']}")
        print("1 - Ver produtos")
        if usuario["papel"] == "admin":
            print("2 - Cadastrar produto")
        else:
            print("2 - Comprar produto(s)")
            print("3 - Ver meus pedidos")
        print("0 - Sair da conta")
        opcao = input("Escolha: ").strip()

        try:
            if opcao == "1":
                listar_produtos(conexao)
            elif opcao == "2" and usuario["papel"] == "admin":
                cadastrar_produto_pelo_menu(conexao, usuario)
            elif opcao == "2" and usuario["papel"] == "cliente":
                comprar_pelo_menu(conexao, usuario)
            elif opcao == "3" and usuario["papel"] == "cliente":
                listar_meus_pedidos(conexao, usuario["id"])
            elif opcao == "0":
                return
            else:
                print("Opção inválida.\n")
        except (ValueError, PermissionError) as erro:
            print(f"Erro: {erro}\n")


def main_cli():
    with banco() as conexao:
        inicializar_banco(conexao)
        criar_administrador_inicial(conexao)

        while True:
            print("=== LOJA VIRTUAL ===")
            print("1 - Entrar")
            print("2 - Criar conta de cliente")
            print("0 - Encerrar")
            opcao = input("Escolha: ").strip()

            if opcao == "1":
                nome = input("Usuário: ").strip()
                senha = ler_senha("Senha: ")
                usuario = autenticar(conexao, nome, senha)
                if usuario:
                    painel_usuario(conexao, usuario)
                else:
                    print(f"{LOGIN_INVALIDO}\n")
            elif opcao == "2":
                nome = input("Crie um nome de usuário: ").strip()
                senha = ler_senha("Crie uma senha (mínimo 8 caracteres): ")
                try:
                    criar_usuario(conexao, nome, senha, papel="cliente")
                    print("Conta criada! Agora você pode entrar.\n")
                except ValueError as erro:
                    print(f"Não foi possível criar a conta: {erro}\n")
                except sqlite3.IntegrityError:
                    print("Não foi possível criar a conta: esse nome de usuário já existe.\n")
            elif opcao == "0":
                print("Loja encerrada.")
                break
            else:
                print("Opção inválida.\n")


def criar_sessao(usuario):
    token = secrets.token_urlsafe(32)
    agora = time.time()
    with SESSOES_WEB_LOCK:
        for chave in [k for k, v in SESSOES_WEB.items() if v["expira"] <= agora]:
            del SESSOES_WEB[chave]
        SESSOES_WEB[token] = {
            "id": usuario["id"],
            "papel": usuario["papel"],
            "nome": usuario["nome_usuario"],
            "expira": agora + DURACAO_SESSAO,
        }
    return token


def login_bloqueado(chave):
    agora = time.time()
    with TENTATIVAS_LOGIN_LOCK:
        recentes = [t for t in TENTATIVAS_LOGIN.get(chave, []) if agora - t < JANELA_LOGIN]
        if recentes:
            TENTATIVAS_LOGIN[chave] = recentes
        else:
            TENTATIVAS_LOGIN.pop(chave, None)
        return len(recentes) >= MAX_TENTATIVAS_LOGIN


def registrar_falha_login(chave):
    with TENTATIVAS_LOGIN_LOCK:
        TENTATIVAS_LOGIN.setdefault(chave, []).append(time.time())


def limpar_falhas_login(chave):
    with TENTATIVAS_LOGIN_LOCK:
        TENTATIVAS_LOGIN.pop(chave, None)


ROTAS_GET = {
    "/api/produtos": "get_produtos",
    "/api/categorias": "get_categorias",
    "/api/me": "get_me",
    "/api/pedidos": "get_pedidos",
}

ROTAS_POST = {
    "/api/contas": "post_conta",
    "/api/login": "post_login",
    "/api/logout": "post_logout",
    "/api/pedidos": "post_pedido",
    "/api/produtos": "post_produto",
    "/api/produtos/estoque": "post_estoque",
    "/api/categorias": "post_categoria",
}


class LojaHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRETORIO_BASE, **kwargs)

    def end_headers(self):
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", POLITICA_CONTEUDO)
        super().end_headers()

    def caminho_requisicao(self):
        return self.path.split("?", 1)[0].split("#", 1)[0]

    def origem_permitida(self):
        origem = self.headers.get("Origin", "")
        if origem == "null":
            return origem
        for prefixo in ("http://127.0.0.1", "http://localhost"):
            if origem == prefixo or origem.startswith(prefixo + ":"):
                return origem
        return ""

    def cabecalhos_cors(self):
        origem = self.origem_permitida()
        if origem:
            self.send_header("Access-Control-Allow-Origin", origem)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def responder_json(self, status, dados):
        conteudo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.cabecalhos_cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(conteudo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(conteudo)

    def ler_json(self):
        try:
            tamanho = int(self.headers.get("Content-Length", "0"))
        except ValueError as erro:
            raise ValueError("Cabeçalho Content-Length inválido.") from erro
        if tamanho < 0 or tamanho > TAMANHO_MAXIMO_REQUISICAO:
            raise ValueError("Requisição muito grande.")
        dados = json.loads(self.rfile.read(tamanho) or b"{}")
        if not isinstance(dados, dict):
            raise ValueError("O corpo da requisição precisa ser um objeto JSON.")
        return dados

    def token_atual(self):
        cabecalho = self.headers.get("Authorization", "")
        if cabecalho.startswith("Bearer "):
            cabecalho = cabecalho[len("Bearer "):]
        return cabecalho.strip()

    def usuario_autenticado(self):
        token = self.token_atual()
        if not token:
            return None
        with SESSOES_WEB_LOCK:
            sessao = SESSOES_WEB.get(token)
            if sessao and sessao["expira"] <= time.time():
                del SESSOES_WEB[token]
                return None
            return sessao

    def exigir_usuario(self, mensagem="Autenticação necessária."):
        usuario = self.usuario_autenticado()
        if usuario is None:
            self.responder_json(401, {"erro": mensagem})
        return usuario

    def despachar(self, rotas, caminho, com_corpo):
        nome_metodo = rotas.get(caminho)
        if nome_metodo is None:
            self.responder_json(404, {"erro": "Rota não encontrada."})
            return
        try:
            self.dados = self.ler_json() if com_corpo else {}
            getattr(self, nome_metodo)()
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.responder_json(400, {"erro": "JSON inválido."})
        except PermissionError as erro:
            self.responder_json(403, {"erro": str(erro)})
        except ValueError as erro:
            self.responder_json(400, {"erro": str(erro)})
        except TypeError:
            self.responder_json(400, {"erro": "Dados inválidos."})
        except sqlite3.OperationalError:
            traceback.print_exc()
            self.responder_json(503, {"erro": "Banco de dados ocupado. Tente novamente."})
        except Exception:
            traceback.print_exc()
            self.responder_json(500, {"erro": "Erro interno do servidor."})

    def caminho_estatico_permitido(self, caminho):
        if caminho in ARQUIVOS_PUBLICOS:
            return True
        caminho = urllib.parse.unquote(caminho)
        return (
            caminho.startswith(PASTA_IMAGENS)
            and not caminho.endswith("/")
            and "\\" not in caminho
            and "\x00" not in caminho
            and posixpath.normpath(caminho) == caminho
        )

    def servir_estatico(self, enviar_corpo):
        if not self.caminho_estatico_permitido(self.caminho_requisicao()):
            self.send_error(404, "Arquivo não encontrado.")
            return
        if enviar_corpo:
            SimpleHTTPRequestHandler.do_GET(self)
        else:
            SimpleHTTPRequestHandler.do_HEAD(self)

    def do_OPTIONS(self):
        self.send_response(204)
        self.cabecalhos_cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        self.servir_estatico(False)

    def do_GET(self):
        caminho = self.caminho_requisicao()
        if caminho.startswith("/api/"):
            self.despachar(ROTAS_GET, caminho, False)
        else:
            self.servir_estatico(True)

    def do_POST(self):
        self.despachar(ROTAS_POST, self.caminho_requisicao(), True)

    def get_produtos(self):
        with banco() as conexao:
            produtos = buscar_produtos(conexao)
        self.responder_json(200, produtos)

    def get_categorias(self):
        with banco() as conexao:
            categorias = buscar_categorias(conexao)
        self.responder_json(200, categorias)

    def get_me(self):
        usuario = self.exigir_usuario()
        if usuario:
            self.responder_json(200, {"usuario": usuario["nome"], "papel": usuario["papel"]})

    def get_pedidos(self):
        usuario = self.exigir_usuario()
        if usuario is None:
            return
        with banco() as conexao:
            pedidos = buscar_pedidos(conexao, usuario["id"])
        self.responder_json(200, pedidos)

    def post_conta(self):
        nome = str(self.dados.get("usuario", "")).strip()
        senha = str(self.dados.get("senha", ""))
        with banco() as conexao:
            try:
                usuario = criar_usuario(conexao, nome, senha)
            except sqlite3.IntegrityError:
                self.responder_json(409, {"erro": "Esse nome de usuário já está em uso."})
                return
        token = criar_sessao(usuario)
        self.responder_json(
            201, {"token": token, "usuario": usuario["nome_usuario"], "papel": usuario["papel"]}
        )

    def post_login(self):
        nome = str(self.dados.get("usuario", ""))
        senha = str(self.dados.get("senha", ""))
        if len(nome) > TAMANHO_MAXIMO_USUARIO or len(senha) > TAMANHO_MAXIMO_SENHA:
            self.responder_json(401, {"erro": LOGIN_INVALIDO})
            return
        chave = (self.client_address[0], nome.strip().lower())
        if login_bloqueado(chave):
            self.responder_json(429, {"erro": "Muitas tentativas. Aguarde alguns minutos e tente de novo."})
            return
        with banco() as conexao:
            usuario = autenticar(conexao, nome, senha)
        if usuario is None:
            registrar_falha_login(chave)
            self.responder_json(401, {"erro": LOGIN_INVALIDO})
            return
        limpar_falhas_login(chave)
        token = criar_sessao(usuario)
        self.responder_json(
            200, {"token": token, "usuario": usuario["nome_usuario"], "papel": usuario["papel"]}
        )

    def post_logout(self):
        with SESSOES_WEB_LOCK:
            SESSOES_WEB.pop(self.token_atual(), None)
        self.responder_json(200, {"mensagem": "Sessão encerrada."})

    def post_pedido(self):
        usuario = self.exigir_usuario("Faça login para finalizar a compra.")
        if usuario is None:
            return
        itens = self.dados.get("itens", [])
        if not isinstance(itens, list):
            raise ValueError("A lista de itens do pedido é inválida.")
        itens_normalizados = []
        for item in itens:
            if not isinstance(item, dict):
                raise ValueError("Formato de item inválido.")
            try:
                itens_normalizados.append(
                    (int(item.get("produto_id")), int(item.get("quantidade")))
                )
            except (TypeError, ValueError) as erro:
                raise ValueError(
                    "Os IDs e as quantidades precisam ser números inteiros."
                ) from erro
        with banco() as conexao:
            pedido_id, total = processar_pedido(conexao, usuario["id"], itens_normalizados)
        self.responder_json(201, {
            "pedido_id": pedido_id,
            "total_centavos": total,
            "total": formatar_preco(total),
        })

    def post_produto(self):
        usuario = self.exigir_usuario()
        if usuario is None:
            return
        exigir_admin(usuario)
        antigo = self.dados.get("preco_antigo")
        with banco() as conexao:
            cadastrar_produto(
                conexao,
                usuario,
                self.dados.get("nome", ""),
                str(self.dados.get("preco", "")),
                self.dados.get("estoque", 0),
                self.dados.get("descricao", ""),
                self.dados.get("imagem", ""),
                "" if antigo is None else str(antigo),
                self.dados.get("categoria_id"),
            )
        self.responder_json(201, {"mensagem": "Produto cadastrado."})

    def post_categoria(self):
        usuario = self.exigir_usuario()
        if usuario is None:
            return
        with banco() as conexao:
            cadastrar_categoria(conexao, usuario, self.dados.get("nome", ""))
        self.responder_json(201, {"mensagem": "Categoria criada."})

    def post_estoque(self):
        usuario = self.exigir_usuario()
        if usuario is None:
            return
        with banco() as conexao:
            atualizar_estoque(
                conexao, usuario, self.dados.get("produto_id"), self.dados.get("estoque")
            )
        self.responder_json(200, {"mensagem": "Estoque atualizado."})

    def log_message(self, formato, *args):
        print("[site] " + formato % args)


def iniciar_api_web(host="0.0.0.0", porta=None):
    if porta is None:
        porta = int(os.environ.get("PORT", "8000"))

    with banco() as conexao:
        inicializar_banco(conexao)
        criar_administrador_inicial(conexao)

    try:
        servidor = ThreadingHTTPServer((host, porta), LojaHandler)
    except OSError as erro:
        print(f"Não foi possível iniciar o servidor em {host}:{porta}: {erro}")
        return
    except OSError as erro:
        print(f"Não foi possível iniciar o servidor em {host}:{porta}: {erro}")
        return

    endereco = f"http://127.0.0.1:{porta}"
    print(f"Loja disponível em {endereco}")
    if host == "0.0.0.0":
        print(f"Na rede local: http://<IP-deste-computador>:{porta}")
    print("Pressione Ctrl+C para encerrar.")
    if "--sem-navegador" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(endereco)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    finally:
        servidor.server_close()


def main():
    verificar_arquivos_sql()
    try:
        preparar_banco("--zerar" in sys.argv)
        if "--cli" in sys.argv:
            main_cli()
        else:
            iniciar_api_web("0.0.0.0" if "--rede" in sys.argv else "127.0.0.1")
    except OSError as erro:
        print(f"Não foi possível acessar o banco de dados ({erro}). Feche outros programas que usem loja.db e tente de novo.")
    except EOFError:
        print(
            "Não foi possível criar o administrador: rode em um terminal interativo "
            "ou defina TRACKFLOW_ADMIN_USER e TRACKFLOW_ADMIN_SENHA."
        )
    except KeyboardInterrupt:
        print("\nEncerrado.")


if __name__ == "__main__":
    main()