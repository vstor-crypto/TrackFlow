INSERT OR IGNORE INTO categorias (nome) VALUES
    ('Eletrônicos'),
    ('Brinquedos'),
    ('Vestuário'),
    ('Esportes'),
    ('Acessórios'),
    ('Veículos');

INSERT INTO produtos (categoria_id, nome, descricao, imagem, preco_centavos, preco_antigo_centavos, estoque) VALUES
    ((SELECT id FROM categorias WHERE nome = 'Eletrônicos'), 'Fone de ouvido sem fio', 'Som de qualidade para acompanhar você.', 'Imagens/fone 2.png', 14990, 19990, 20),
    ((SELECT id FROM categorias WHERE nome = 'Eletrônicos'), 'Anel inteligente Halo com case', 'Acompanhe sono e atividade direto do dedo.', 'Imagens/halo.webp', 129900, NULL, 12),
    ((SELECT id FROM categorias WHERE nome = 'Eletrônicos'), 'Filmadora profissional 4K', 'Lente com zoom, microfone integrado e controles completos.', 'Imagens/xf605.webp', 2899000, NULL, 3),
    ((SELECT id FROM categorias WHERE nome = 'Eletrônicos'), 'Robô humanoide Optimus', 'Robô humanoide para tarefas do dia a dia.', 'Imagens/optimus.webp', 15000000, NULL, 2),
    ((SELECT id FROM categorias WHERE nome = 'Eletrônicos'), 'Console PlayStation 5 Slim Digital', 'Jogos em alta resolução com controle sem fio incluso.', 'Imagens/ps5.webp', 379900, 429900, 10),
    ((SELECT id FROM categorias WHERE nome = 'Eletrônicos'), 'Nintendo Switch 2', 'Jogue na TV ou onde você estiver.', 'Imagens/switch.webp', 449900, NULL, 7),
    ((SELECT id FROM categorias WHERE nome = 'Eletrônicos'), 'Óculos de realidade virtual', 'Imersão total com controles sem fio.', 'Imagens/meta.webp', 299900, 349900, 6),
    ((SELECT id FROM categorias WHERE nome = 'Eletrônicos'), 'PC gamer Titan dourado', 'Gabinete dourado com refrigeração líquida e alto desempenho.', 'Imagens/titan.jpg', 1899000, NULL, 2),
    ((SELECT id FROM categorias WHERE nome = 'Brinquedos'), 'LEGO One Piece Going Merry', 'Monte o navio dos Chapéus de Palha com 1.376 peças.', 'Imagens/legoo.webp', 119900, 139900, 8),
    ((SELECT id FROM categorias WHERE nome = 'Brinquedos'), 'Cama elástica colorida', 'Diversão ao ar livre para toda a família.', 'Imagens/pula.jpg', 129900, NULL, 5),
    ((SELECT id FROM categorias WHERE nome = 'Vestuário'), 'Camisa de treino Nike preta', 'Tecido leve que seca rápido.', 'Imagens/nike.jpg', 12990, NULL, 40),
    ((SELECT id FROM categorias WHERE nome = 'Vestuário'), 'Camisa do Flamengo preta e dourada', 'Camisa preta com detalhes dourados e escudo do clube.', 'Imagens/flamengo.webp', 34990, 39990, 25),
    ((SELECT id FROM categorias WHERE nome = 'Esportes'), 'Bola de futebol Copa do Mundo', 'Bola oficial para jogar com a turma.', 'Imagens/bola.jpg', 34990, 42990, 25),
    ((SELECT id FROM categorias WHERE nome = 'Esportes'), 'Kit de paintball completo', 'Marcadora, máscara, colete, CO2 e munição.', 'Imagens/paint_ball.jpg', 189900, 229900, 5),
    ((SELECT id FROM categorias WHERE nome = 'Acessórios'), 'Mochila para o dia a dia', 'Praticidade e espaço para a sua rotina.', 'Imagens/bolsa 2.png', 12990, NULL, 15),
    ((SELECT id FROM categorias WHERE nome = 'Acessórios'), 'Garrafa térmica', 'Mantenha sua bebida na temperatura ideal.', 'Imagens/garrafa 2.png', 7990, NULL, 30),
    ((SELECT id FROM categorias WHERE nome = 'Acessórios'), 'Óculos esportivo Mormaii Smash', 'Lentes escuras e acessórios extras para o esporte.', 'Imagens/mormaii_smash.webp', 49900, 59900, 14),
    ((SELECT id FROM categorias WHERE nome = 'Veículos'), 'Tesla Roadster', 'Um superesportivo 100% elétrico desenvolvido pela Tesla. A nova versão redesenhada e apresentada pela fabricante em outubro de 2026 traz tecnologias aerodinâmicas avançadas e propulsão inspirada em foguetes da SpaceX.', 'Imagens/carro.png', 100000000, NULL, 2),
    ((SELECT id FROM categorias WHERE nome = 'Veículos'), 'Moto custom Harley-Davidson azul', 'Edição exclusiva com acabamento azul e detalhes em cobre.', 'Imagens/harley.jpg', 28000000, NULL, 1);