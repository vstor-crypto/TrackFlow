# Track Flow — loja virtual

Python 3.8+ (sem bibliotecas externas), SQLite, HTML/CSS/JS puro.

## Como rodar
```
python app.py              # abre http://127.0.0.1:8000
python app.py --rede       # permite acessar de outros aparelhos da rede (celular da banca)
python app.py --zerar      # apaga o banco e recria com os produtos iniciais
python app.py --cli        # versão em terminal
```
Na primeira execução o terminal pede o usuário e a senha do **administrador**.
Para automatizar: defina `TRACKFLOW_ADMIN_USER` e `TRACKFLOW_ADMIN_SENHA`.

## Estrutura da pasta
```
app.py  schema.sql  DI.sql  index.html  style.css  script.js  Imagens/   (loja.db é gerado)
```
- `app.py` lê **schema.sql** (tabelas) e **DI.sql** (categorias e produtos iniciais). Para mudar os produtos de exemplo, edite o `DI.sql` e rode `python app.py --zerar`.
- `Imagens/` precisa estar ao lado do `app.py`, com os nomes iguais aos do `DI.sql` (ex.: `fone 2.png`). Se a imagem não carregar, a loja mostra um aviso no lugar. Falta o `conjunto.png` do banner; sem ele o banner mostra só o texto.

## Categorias
Eletrônicos, Brinquedos, Vestuário, Esportes, Acessórios e Veículos (criadas pelo `DI.sql`). A vitrine mostra um botão de filtro, com a contagem, só para categorias que têm produtos, e a busca também procura pelo nome da categoria. O admin cria novas categorias e escolhe a categoria ao cadastrar cada produto.

## Roteiro de demonstração (3 min)
1. Home, ofertas, filtro por categoria e busca (digitar "fone").
2. Criar conta de cliente, adicionar produtos, usar +/−, finalizar pedido.
3. "Meus pedidos" mostra o histórico; o estoque caiu.
4. Sair, entrar como admin: cadastrar produto (com preço antigo = aparece em Ofertas), criar categoria nova e ajustar estoque.

## O que a banca pode perguntar
- Senhas: PBKDF2-SHA256, 200 mil iterações, sal aleatório por usuário, comparação em tempo constante.
- SQL injection: todas as consultas usam parâmetros (`?`).
- XSS: o front usa `textContent`, nunca `innerHTML`; o servidor envia Content-Security-Policy.
- Dinheiro: guardado em centavos (inteiro), sem float.
- Preço e estoque são validados no servidor; o total do pedido é calculado no servidor.
- Compra concorrente: `BEGIN IMMEDIATE` + `UPDATE ... WHERE estoque >= ?` evitam estoque negativo.
- Força bruta: 5 tentativas de login erradas bloqueiam por 5 minutos.

## Limitações conhecidas (diga antes que perguntem)
- Sessões ficam na memória: reiniciar o servidor desloga todos.
- Sem pagamento real nem HTTPS (uso local/demonstração).
- Um banco incompatível com o esquema do `app.py` é movido para `loja.db.<data>.bak`, não apagado.
