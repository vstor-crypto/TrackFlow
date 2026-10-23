(() => {
	"use strict";

	const CHAVE_TOKEN = "trackflow-token";
	const CHAVE_CARRINHO = "trackflow-carrinho";
	const IMAGEM_INDISPONIVEL = "data:image/svg+xml;utf8," + encodeURIComponent(
		'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300"><rect width="100%" height="100%" fill="#f5d4dc"/>' +
		'<text x="50%" y="50%" fill="#74132f" font-family="Arial" font-size="18" text-anchor="middle">Imagem indisponível</text></svg>'
	);
	const BASE_PADRAO = "http://127.0.0.1:8000";
	const DICA_SERVIDOR = "Rode python app.py e abra http://127.0.0.1:8000.";
	const TEXTO_PEDIDOS_SAIDA = "Entre na sua conta para ver seus pedidos.";
	const TEXTO_CONTA_SAIDA = "Entre ou crie uma conta para finalizar sua compra.";

	const $ = (seletor) => document.querySelector(seletor);

	const el = {
		aviso: $("#aviso-servidor"),
		textoAviso: $("#texto-aviso"),
		tentarNovamente: $("#tentar-novamente"),
		modeloProduto: $("#modelo-produto"),
		listaProdutos: $("#lista-produtos"),
		statusProdutos: $("#status-produtos"),
		listaOfertas: $("#lista-ofertas"),
		statusOfertas: $("#status-ofertas"),
		listaCarrinho: $("#itens-carrinho"),
		statusCarrinho: $("#status-carrinho"),
		contador: $(".carrinho .contador"),
		finalizar: $("#finalizar-pedido"),
		statusConta: $("#status-conta"),
		formLogin: $("#form-login"),
		formRegistro: $("#form-registro"),
		sair: $("#sair-conta"),
		statusPedidos: $("#status-pedidos"),
		listaPedidos: $("#lista-pedidos"),
		formBusca: $('form[role="search"]'),
		campoBusca: $("#busca"),
		linkCarrinho: $(".carrinho"),
		imagemBanner: $(".banner-imagens img"),
		navAdmin: $("#nav-admin"),
		secaoAdmin: $("#admin"),
		statusAdmin: $("#status-admin"),
		formProduto: $("#form-produto"),
		listaEstoque: $("#lista-estoque"),
		filtros: $("#filtros-categoria"),
		selectCategoria: $("#produto-categoria"),
		formCategoria: $("#form-categoria")
	};

	const carrinho = new Map(lerCarrinhoSalvo());
	let produtos = [];
	let categorias = [];
	let categoriaAtiva = 0;
	let token = lerToken();
	let usuarioAtual = null;
	let papelAtual = null;
	let baseApi = null;

	function lerCarrinhoSalvo() {
		try {
			const dados = JSON.parse(localStorage.getItem(CHAVE_CARRINHO) || "[]");
			return Array.isArray(dados)
				? dados.filter(([id, qtd]) => Number.isInteger(id) && Number.isInteger(qtd) && qtd > 0)
				: [];
		} catch {
			return [];
		}
	}

	function salvarCarrinho() {
		try {
			localStorage.setItem(CHAVE_CARRINHO, JSON.stringify([...carrinho]));
		} catch {}
	}

	function lerToken() {
		try {
			return localStorage.getItem(CHAVE_TOKEN);
		} catch {
			return null;
		}
	}

	function salvarToken(valor) {
		token = valor;
		try {
			if (valor) localStorage.setItem(CHAVE_TOKEN, valor);
			else localStorage.removeItem(CHAVE_TOKEN);
		} catch {}
	}

	const formatarPreco = (centavos) =>
		(centavos / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

	function formatarData(iso) {
		const data = new Date(iso);
		if (Number.isNaN(data.getTime())) return "";
		return data.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
	}

	function criar(tag, texto = "", classe = "") {
		const elemento = document.createElement(tag);
		if (texto) elemento.textContent = texto;
		if (classe) elemento.className = classe;
		return elemento;
	}

	function mostrarAviso(texto) {
		el.textoAviso.textContent = texto;
		el.aviso.hidden = !texto;
	}

	function erroDeConexao(mensagem) {
		const erro = new Error(mensagem);
		erro.conexao = true;
		return erro;
	}

	function basesCandidatas() {
		const bases = [];
		if (location.protocol !== "file:") bases.push("");
		if (location.origin !== BASE_PADRAO) bases.push(BASE_PADRAO);
		return bases;
	}

	async function requisitar(base, url, opcoes) {
		const headers = { "Content-Type": "application/json", ...(opcoes.headers || {}) };
		if (token) headers.Authorization = `Bearer ${token}`;

		let resposta;
		try {
			resposta = await fetch(base + url, { ...opcoes, headers });
		} catch {
			throw erroDeConexao(`Não foi possível conectar ao servidor da loja. ${DICA_SERVIDOR}`);
		}

		const tipo = resposta.headers.get("Content-Type") || "";
		if (!tipo.includes("json")) {
			throw erroDeConexao(`Esta página não está sendo servida pelo app.py (HTTP ${resposta.status}). ${DICA_SERVIDOR}`);
		}

		let dados;
		try {
			dados = await resposta.json();
		} catch {
			throw erroDeConexao(`Resposta inválida do servidor (HTTP ${resposta.status}). ${DICA_SERVIDOR}`);
		}

		if (!resposta.ok) {
			const erro = new Error(dados.erro || `Falha na comunicação com a loja (HTTP ${resposta.status}).`);
			erro.status = resposta.status;
			throw erro;
		}
		return dados;
	}

	async function api(url, opcoes = {}) {
		if (baseApi !== null) return requisitar(baseApi, url, opcoes);

		let ultimoErro = erroDeConexao(`Não foi possível conectar ao servidor da loja. ${DICA_SERVIDOR}`);
		for (const base of basesCandidatas()) {
			try {
				const dados = await requisitar(base, url, opcoes);
				baseApi = base;
				return dados;
			} catch (erro) {
				if (!erro.conexao) {
					baseApi = base;
					throw erro;
				}
				ultimoErro = erro;
			}
		}
		throw ultimoErro;
	}

	function renderizarFiltros() {
		el.filtros.replaceChildren();

		const comProdutos = categorias.filter((c) => produtos.some((p) => p.categoria_id === c.id));
		if (!comProdutos.length) {
			categoriaAtiva = 0;
			return;
		}
		if (categoriaAtiva && !comProdutos.some((c) => c.id === categoriaAtiva)) categoriaAtiva = 0;

		const opcoes = [{ id: 0, nome: "Todos", total: produtos.length }].concat(
			comProdutos.map((c) => ({ ...c, total: produtos.filter((p) => p.categoria_id === c.id).length }))
		);

		for (const opcao of opcoes) {
			const botao = criar("button", `${opcao.nome} (${opcao.total})`);
			botao.type = "button";
			botao.setAttribute("aria-pressed", String(opcao.id === categoriaAtiva));
			botao.addEventListener("click", () => {
				categoriaAtiva = opcao.id;
				renderizarFiltros();
				aplicarBusca();
			});
			el.filtros.append(botao);
		}
	}

	function renderizarSelectCategorias() {
		const atual = el.selectCategoria.value;
		el.selectCategoria.replaceChildren();
		for (const categoria of categorias) {
			const opcao = criar("option", categoria.nome);
			opcao.value = String(categoria.id);
			el.selectCategoria.append(opcao);
		}
		if (atual) el.selectCategoria.value = atual;
	}

	function renderizarProdutos() {
		el.listaProdutos.replaceChildren();
		renderizarFiltros();

		for (const produto of produtos) {
			const fragmento = el.modeloProduto.content.cloneNode(true);
			const artigo = fragmento.querySelector("article");
			const imagem = artigo.querySelector("img");
			const precoAntigo = artigo.querySelector("del");
			const botao = artigo.querySelector("button");
			const semEstoque = produto.estoque <= 0;

			artigo.id = `produto-${produto.id}`;
			fragmento.querySelector("li").dataset.categoria = String(produto.categoria_id);
			artigo.querySelector(".categoria").textContent = produto.categoria;

			if (produto.imagem) {
				imagem.addEventListener("error", () => { imagem.src = IMAGEM_INDISPONIVEL; }, { once: true });
				imagem.src = produto.imagem;
				imagem.alt = produto.nome;
			} else {
				imagem.remove();
			}

			artigo.querySelector("h3").textContent = produto.nome;
			artigo.querySelector(".descricao").textContent = produto.descricao;
			artigo.querySelector("strong").textContent = formatarPreco(produto.preco_centavos);

			if (produto.preco_antigo_centavos) precoAntigo.textContent = formatarPreco(produto.preco_antigo_centavos);
			else precoAntigo.remove();

			botao.disabled = semEstoque;
			botao.textContent = semEstoque ? "Indisponível" : "Adicionar ao carrinho";
			botao.addEventListener("click", () => adicionarAoCarrinho(produto.id));

			el.listaProdutos.append(fragmento);
		}

		aplicarBusca();
	}

	function renderizarOfertas() {
		el.listaOfertas.replaceChildren();
		const ofertas = produtos.filter((produto) => produto.preco_antigo_centavos);

		el.statusOfertas.textContent = ofertas.length ? "" : "Nenhuma oferta no momento.";

		for (const produto of ofertas) {
			const item = criar("li");
			const link = criar("a", produto.nome);
			link.href = `#produto-${produto.id}`;
			item.append(
				link,
				` por ${formatarPreco(produto.preco_centavos)} (de ${formatarPreco(produto.preco_antigo_centavos)})`
			);
			el.listaOfertas.append(item);
		}
	}

	function aplicarBusca(rolar = false) {
		const consulta = el.campoBusca.value.trim().toLocaleLowerCase("pt-BR");
		let encontrados = 0;

		for (const item of el.listaProdutos.children) {
			const texto = `${item.querySelector("h3").textContent} ${item.querySelector(".descricao").textContent} ${item.querySelector(".categoria").textContent}`;
			const naCategoria = !categoriaAtiva || Number(item.dataset.categoria) === categoriaAtiva;
			const visivel = naCategoria && (!consulta || texto.toLocaleLowerCase("pt-BR").includes(consulta));
			item.hidden = !visivel;
			if (visivel) encontrados += 1;
		}

		if (produtos.length) {
			el.statusProdutos.textContent = consulta || categoriaAtiva
				? encontrados
					? `${encontrados} produto(s) encontrado(s).`
					: "Nenhum produto encontrado."
				: "";
		}

		if (rolar) $("#produtos").scrollIntoView({ behavior: "smooth" });
	}

	function botaoAcao(texto, rotulo, aoClicar) {
		const botao = criar("button", texto);
		botao.type = "button";
		botao.setAttribute("aria-label", rotulo);
		botao.addEventListener("click", aoClicar);
		return botao;
	}

	function renderizarCarrinho() {
		el.listaCarrinho.replaceChildren();
		let quantidadeTotal = 0;
		let totalCentavos = 0;

		for (const [id, quantidade] of carrinho) {
			const produto = produtos.find((p) => p.id === id);
			if (!produto) {
				carrinho.delete(id);
				continue;
			}

			quantidadeTotal += quantidade;
			totalCentavos += produto.preco_centavos * quantidade;

			const linha = criar("li");
			const descricao = criar("span", `${produto.nome} — ${quantidade} × ${formatarPreco(produto.preco_centavos)}`);
			const acoes = criar("span", "", "acoes-carrinho");
			acoes.append(
				botaoAcao("−", `Diminuir a quantidade de ${produto.nome}`, () => removerDoCarrinho(id)),
				botaoAcao("+", `Aumentar a quantidade de ${produto.nome}`, () => adicionarAoCarrinho(id)),
				botaoAcao("Remover", `Remover ${produto.nome} do carrinho`, () => removerTudo(id))
			);

			linha.append(descricao, acoes);
			el.listaCarrinho.append(linha);
		}

		el.contador.textContent = String(quantidadeTotal);
		el.linkCarrinho.setAttribute("aria-label", `Carrinho, ${quantidadeTotal} item(ns)`);
		el.statusCarrinho.textContent = quantidadeTotal
			? `${quantidadeTotal} item(ns) no carrinho. Total: ${formatarPreco(totalCentavos)}`
			: "Seu carrinho está vazio.";
	}

	function adicionarAoCarrinho(id) {
		const produto = produtos.find((p) => p.id === id);
		if (!produto) return;

		const quantidade = carrinho.get(id) || 0;
		if (quantidade >= produto.estoque) {
			el.statusCarrinho.textContent = `Estoque insuficiente de "${produto.nome}".`;
			return;
		}

		carrinho.set(id, quantidade + 1);
		salvarCarrinho();
		renderizarCarrinho();
	}

	function removerTudo(id) {
		carrinho.delete(id);
		salvarCarrinho();
		renderizarCarrinho();
	}

	function removerDoCarrinho(id) {
		const quantidade = carrinho.get(id) || 0;
		if (quantidade > 1) carrinho.set(id, quantidade - 1);
		else carrinho.delete(id);
		salvarCarrinho();
		renderizarCarrinho();
	}

	function ajustarCarrinhoAoEstoque() {
		for (const [id, quantidade] of [...carrinho]) {
			const produto = produtos.find((p) => p.id === id);
			if (!produto || produto.estoque <= 0) carrinho.delete(id);
			else if (quantidade > produto.estoque) carrinho.set(id, produto.estoque);
		}
	}

	async function carregarProdutos() {
		el.finalizar.disabled = true;
		try {
			const lista = await api("/api/produtos");
			const listaCategorias = await api("/api/categorias");
			if (!Array.isArray(lista) || !Array.isArray(listaCategorias)) throw new Error("Lista de produtos inválida.");

			produtos = lista;
			categorias = listaCategorias;
			renderizarSelectCategorias();
			mostrarAviso("");
			ajustarCarrinhoAoEstoque();
			salvarCarrinho();
			el.statusProdutos.textContent = produtos.length ? "" : "Nenhum produto cadastrado.";
			renderizarProdutos();
			renderizarOfertas();
			renderizarCarrinho();
			renderizarEstoque();
			el.finalizar.disabled = false;
			return true;
		} catch (erro) {
			produtos = [];
			categorias = [];
			carrinho.clear();
			mostrarAviso(erro.conexao ? `Servidor da loja indisponível. ${erro.message}` : `Não foi possível carregar os produtos: ${erro.message}`);
			el.statusProdutos.textContent = "Produtos indisponíveis no momento.";
			el.statusOfertas.textContent = "Ofertas indisponíveis no momento.";
			renderizarProdutos();
			renderizarOfertas();
			renderizarCarrinho();
			return false;
		}
	}

	function atualizarConta(nome = null, papel = null) {
		usuarioAtual = nome;
		papelAtual = nome ? papel : null;
		const conectado = Boolean(nome);
		const admin = papelAtual === "admin";
		el.secaoAdmin.hidden = !admin;
		el.navAdmin.hidden = !admin;
		renderizarEstoque();
		el.formLogin.hidden = conectado;
		el.formRegistro.hidden = conectado;
		el.sair.hidden = !conectado;
		el.statusConta.textContent = conectado
			? `Conectado como ${nome}${admin ? " (administrador)" : ""}.`
			: TEXTO_CONTA_SAIDA;
	}

	function limparPedidos() {
		el.listaPedidos.replaceChildren();
		el.statusPedidos.textContent = TEXTO_PEDIDOS_SAIDA;
	}

	function encerrarSessaoLocal(mensagem = "") {
		salvarToken(null);
		atualizarConta();
		limparPedidos();
		if (mensagem) el.statusConta.textContent = mensagem;
	}

	function criarCartaoPedido(pedido) {
		const cartao = criar("li", "", "pedido");
		const topo = criar("div", "", "pedido-topo");
		const data = criar("time", formatarData(pedido.data));
		const itens = criar("ul", "", "pedido-itens");

		data.dateTime = pedido.data;
		topo.append(criar("h3", `Pedido #${pedido.id}`), data);

		for (const item of pedido.itens) {
			itens.append(
				criar("li", `${item.nome} — ${item.quantidade} × ${formatarPreco(item.preco_unitario_centavos)}`)
			);
		}

		cartao.append(topo, itens, criar("p", `Total: ${formatarPreco(pedido.total_centavos)}`, "pedido-total"));
		return cartao;
	}

	async function carregarPedidos() {
		el.listaPedidos.replaceChildren();
		if (!usuarioAtual) {
			el.statusPedidos.textContent = TEXTO_PEDIDOS_SAIDA;
			return;
		}

		el.statusPedidos.textContent = "Carregando pedidos...";
		try {
			const pedidos = await api("/api/pedidos");
			if (!Array.isArray(pedidos)) throw new Error("Lista de pedidos inválida.");

			el.statusPedidos.textContent = pedidos.length
				? `${pedidos.length} pedido(s) realizado(s).`
				: "Você ainda não fez pedidos.";
			for (const pedido of pedidos) el.listaPedidos.append(criarCartaoPedido(pedido));
		} catch (erro) {
			if (erro.status === 401) encerrarSessaoLocal("Sua sessão expirou. Entre novamente.");
			else el.statusPedidos.textContent = `Não foi possível carregar os pedidos: ${erro.message}`;
		}
	}

	async function validarSessao() {
		if (!token) {
			atualizarConta();
			limparPedidos();
			return;
		}
		try {
			const dados = await api("/api/me");
			atualizarConta(dados.usuario, dados.papel);
			await carregarPedidos();
		} catch (erro) {
			if (erro.status === 401) salvarToken(null);
			atualizarConta();
			limparPedidos();
		}
	}

	async function enviarFormulario(evento, rota) {
		evento.preventDefault();
		const formulario = evento.currentTarget;
		const botao = formulario.querySelector('button[type="submit"]');
		const dados = new FormData(formulario);

		botao.disabled = true;
		try {
			const resultado = await api(rota, {
				method: "POST",
				body: JSON.stringify({ usuario: dados.get("usuario"), senha: dados.get("senha") })
			});
			salvarToken(resultado.token);
			formulario.reset();
			atualizarConta(resultado.usuario, resultado.papel);
			await carregarPedidos();
		} catch (erro) {
			el.statusConta.textContent = erro.message;
		} finally {
			botao.disabled = false;
		}
	}

	function renderizarEstoque() {
		el.listaEstoque.replaceChildren();
		if (papelAtual !== "admin") return;

		for (const produto of produtos) {
			const linha = criar("li", "", "linha-estoque");
			const rotulo = criar("label", produto.nome);
			const campo = criar("input");
			const salvar = criar("button", "Salvar");

			campo.id = `estoque-${produto.id}`;
			campo.type = "number";
			campo.min = "0";
			campo.max = "1000000";
			campo.step = "1";
			campo.value = produto.estoque;
			rotulo.htmlFor = campo.id;
			salvar.type = "button";
			salvar.addEventListener("click", () => atualizarEstoque(produto.id, campo.value, salvar));

			linha.append(rotulo, campo, salvar);
			el.listaEstoque.append(linha);
		}
	}

	function erroAdmin(erro) {
		if (erro.status === 401) {
			encerrarSessaoLocal("Sua sessão expirou. Entre novamente.");
			$("#conta").scrollIntoView({ behavior: "smooth" });
		} else {
			el.statusAdmin.textContent = erro.message;
		}
	}

	async function atualizarEstoque(id, valor, botao) {
		const numero = Number(valor);
		if (valor.trim() === "" || !Number.isInteger(numero) || numero < 0) {
			el.statusAdmin.textContent = "Informe um estoque inteiro, maior ou igual a zero.";
			return;
		}
		botao.disabled = true;
		try {
			await api("/api/produtos/estoque", {
				method: "POST",
				body: JSON.stringify({ produto_id: id, estoque: numero })
			});
			await carregarProdutos();
			el.statusAdmin.textContent = "Estoque atualizado.";
		} catch (erro) {
			erroAdmin(erro);
		} finally {
			botao.disabled = false;
		}
	}

	async function cadastrarProduto(evento) {
		evento.preventDefault();
		const formulario = evento.currentTarget;
		const botao = formulario.querySelector('button[type="submit"]');
		const dados = new FormData(formulario);

		botao.disabled = true;
		try {
			await api("/api/produtos", {
				method: "POST",
				body: JSON.stringify({
					categoria_id: dados.get("categoria_id"),
					nome: dados.get("nome"),
					descricao: dados.get("descricao"),
					imagem: dados.get("imagem"),
					preco: dados.get("preco"),
					preco_antigo: dados.get("preco_antigo"),
					estoque: dados.get("estoque")
				})
			});
			formulario.reset();
			await carregarProdutos();
			el.statusAdmin.textContent = "Produto cadastrado.";
		} catch (erro) {
			erroAdmin(erro);
		} finally {
			botao.disabled = false;
		}
	}

	async function criarCategoria(evento) {
		evento.preventDefault();
		const formulario = evento.currentTarget;
		const botao = formulario.querySelector('button[type="submit"]');
		const dados = new FormData(formulario);

		botao.disabled = true;
		try {
			await api("/api/categorias", {
				method: "POST",
				body: JSON.stringify({ nome: dados.get("nome") })
			});
			formulario.reset();
			await carregarProdutos();
			el.statusAdmin.textContent = "Categoria criada.";
		} catch (erro) {
			erroAdmin(erro);
		} finally {
			botao.disabled = false;
		}
	}

	async function finalizarPedido() {
		if (!carrinho.size) {
			el.statusCarrinho.textContent = "Adicione produtos antes de finalizar o pedido.";
			return;
		}
		if (papelAtual === "admin") {
			el.statusCarrinho.textContent = "Contas de administrador não finalizam pedidos. Entre com uma conta de cliente.";
			return;
		}
		if (!usuarioAtual) {
			el.statusConta.textContent = "Entre ou crie uma conta para finalizar a compra.";
			$("#conta").scrollIntoView({ behavior: "smooth" });
			return;
		}

		el.finalizar.disabled = true;
		try {
			const itens = [...carrinho].map(([produto_id, quantidade]) => ({ produto_id, quantidade }));
			const pedido = await api("/api/pedidos", { method: "POST", body: JSON.stringify({ itens }) });

			carrinho.clear();
			salvarCarrinho();
			await carregarProdutos();
			el.statusCarrinho.textContent = `Pedido #${pedido.pedido_id} confirmado. Total: ${pedido.total}`;
			await carregarPedidos();
		} catch (erro) {
			if (erro.status === 401) {
				encerrarSessaoLocal("Sua sessão expirou. Entre novamente para finalizar a compra.");
				$("#conta").scrollIntoView({ behavior: "smooth" });
			}
			el.statusCarrinho.textContent = erro.message;
			el.finalizar.disabled = false;
		}
	}

	async function sairDaConta() {
		try {
			await api("/api/logout", { method: "POST", body: "{}" });
		} catch {}
		encerrarSessaoLocal("Você saiu da sua conta.");
	}

	async function iniciar() {
		renderizarCarrinho();
		const servidorOnline = await carregarProdutos();
		if (servidorOnline) {
			await validarSessao();
		} else {
			atualizarConta();
			limparPedidos();
		}
	}

	el.formBusca.addEventListener("submit", (evento) => {
		evento.preventDefault();
		aplicarBusca(true);
	});

	el.campoBusca.addEventListener("search", () => aplicarBusca());
	el.campoBusca.addEventListener("input", () => aplicarBusca());
	el.formProduto.addEventListener("submit", cadastrarProduto);
	el.formCategoria.addEventListener("submit", criarCategoria);
	if (el.imagemBanner) el.imagemBanner.addEventListener("error", () => { el.imagemBanner.hidden = true; });
	el.formLogin.addEventListener("submit", (evento) => enviarFormulario(evento, "/api/login"));
	el.formRegistro.addEventListener("submit", (evento) => enviarFormulario(evento, "/api/contas"));
	el.sair.addEventListener("click", sairDaConta);
	el.finalizar.addEventListener("click", finalizarPedido);
	el.tentarNovamente.addEventListener("click", iniciar);

	iniciar();
})();