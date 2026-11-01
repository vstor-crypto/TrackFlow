INSERT OR IGNORE INTO categorias (nome) VALUES
    ('Eletrônicos'),
    ('Brinquedos'),
    ('Vestuário'),
    ('Esportes'),
    ('Acessórios'),
    ('Veículos');

INSERT INTO produtos (categoria_id, nome, descricao, imagem, preco_centavos, preco_antigo_centavos, estoque) VALUES
    ((SELECT id FROM categorias WHERE nome = 'Eletrônicos'), 'Fone de ouvido sem fio', 'Som de qualidade para acompanhar você.', 'Imagens/fone 2.png', 14990, 19990, 20),
    ((SELECT id FROM categorias WHERE nome = 'Acessórios'), 'Mochila para o dia a dia', 'Praticidade e espaço para a sua rotina.', 'Imagens/bolsa 2.png', 12990, NULL, 15),
    ((SELECT id FROM categorias WHERE nome = 'Acessórios'), 'Garrafa térmica', 'Mantenha sua bebida na temperatura ideal.', 'Imagens/garrafa 2.png', 7990, NULL, 30);
