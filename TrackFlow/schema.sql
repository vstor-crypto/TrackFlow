CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_usuario TEXT NOT NULL UNIQUE COLLATE NOCASE,
    sal TEXT NOT NULL,
    hash_senha TEXT NOT NULL,
    papel TEXT NOT NULL CHECK (papel IN ('admin', 'cliente'))
);

CREATE TABLE IF NOT EXISTS categorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS produtos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria_id INTEGER NOT NULL,
    nome TEXT NOT NULL UNIQUE,
    descricao TEXT NOT NULL DEFAULT '',
    imagem TEXT NOT NULL DEFAULT '',
    preco_centavos INTEGER NOT NULL CHECK (preco_centavos > 0),
    preco_antigo_centavos INTEGER CHECK (preco_antigo_centavos IS NULL OR preco_antigo_centavos > preco_centavos),
    estoque INTEGER NOT NULL CHECK (estoque >= 0),
    FOREIGN KEY (categoria_id) REFERENCES categorias(id)
);

CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    data_criacao TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_centavos INTEGER NOT NULL CHECK (total_centavos >= 0),
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

CREATE TABLE IF NOT EXISTS itens_pedido (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id INTEGER NOT NULL,
    produto_id INTEGER NOT NULL,
    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
    preco_unitario_centavos INTEGER NOT NULL CHECK (preco_unitario_centavos > 0),
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id),
    FOREIGN KEY (produto_id) REFERENCES produtos(id)
);

CREATE INDEX IF NOT EXISTS idx_produtos_categoria ON produtos(categoria_id);
CREATE INDEX IF NOT EXISTS idx_pedidos_usuario ON pedidos(usuario_id);
CREATE INDEX IF NOT EXISTS idx_itens_pedido ON itens_pedido(pedido_id);

CREATE VIEW IF NOT EXISTS vw_pedidos_detalhados AS
SELECT
    pedidos.id AS pedido_id,
    pedidos.usuario_id,
    pedidos.data_criacao,
    pedidos.total_centavos,
    itens_pedido.produto_id,
    produtos.nome AS produto_nome,
    itens_pedido.quantidade,
    itens_pedido.preco_unitario_centavos
FROM pedidos
JOIN itens_pedido ON itens_pedido.pedido_id = pedidos.id
JOIN produtos ON produtos.id = itens_pedido.produto_id;