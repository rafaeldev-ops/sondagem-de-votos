// O JWT do admin NÃO passa mais por aqui: ele vive num cookie httpOnly
// que este script não consegue ler. Antes ficava em localStorage, de onde
// um XSS o levava com uma linha de script e o reutilizava fora do
// navegador da vítima.
//
// O que este arquivo lê é o cookie de CSRF, que é legível de propósito e
// não autentica nada sozinho — ver validate_csrf() em app/api/deps.py.

const loginSection = document.getElementById('loginSection');
const dashboardSection = document.getElementById('dashboardSection');
const btnLogout = document.getElementById('btnLogout');

// Defesa em profundidade: nunca interpolar texto vindo da API direto em
// innerHTML sem escapar, mesmo que o backend já sanitize na gravação.
function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value ?? '';
    return div.innerHTML;
}

function csrfToken() {
    const match = document.cookie.match(/(?:^|;\s*)admin_csrf=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : '';
}

// Requisições que só leem não precisam de CSRF; as que alteram estado
// mandam o header que o servidor compara com o cookie.
function csrfHeaders() {
    return { 'X-CSRF-Token': csrfToken() };
}

function showDashboard() {
    loginSection.classList.add('d-none');
    dashboardSection.classList.remove('d-none');
    btnLogout.classList.remove('d-none');
    loadStats();
    loadCandidatos();
}

function showLogin() {
    loginSection.classList.remove('d-none');
    dashboardSection.classList.add('d-none');
    btnLogout.classList.add('d-none');
}

async function logout() {
    // Só o servidor consegue apagar o cookie httpOnly.
    await fetch('/api/admin/logout', { method: 'POST', headers: csrfHeaders() });
    showLogin();
}

// Sem localStorage para consultar, a sessão é verificada perguntando ao
// servidor: se o cookie ainda vale, /stats responde 200. Isso também
// cobre o caso do JWT ter expirado com o cookie ainda presente.
async function init() {
    const res = await fetch('/api/admin/stats');
    if (res.ok) {
        showDashboard();
    } else {
        showLogin();
    }
}

init();

document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const res = await fetch('/api/admin/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            username: document.getElementById('adminUser').value,
            password: document.getElementById('adminPass').value,
        }),
    });

    if (!res.ok) {
        alert('Credenciais inválidas');
        return;
    }

    // A resposta ainda traz access_token no corpo, para quem autentica por
    // bearer fora do navegador. O painel ignora: o que interessa é o
    // cookie que veio no Set-Cookie desta mesma resposta.
    document.getElementById('loginForm').reset();
    showDashboard();
});

btnLogout.addEventListener('click', logout);

async function loadStats() {
    const res = await fetch('/api/admin/stats');
    if (!res.ok) return showLogin();
    const data = await res.json();
    document.getElementById('statRespostas').textContent = data.total_respostas;
    document.getElementById('statAtivos').textContent = data.total_candidatos_ativos;
    document.getElementById('statTotal').textContent = data.total_candidatos;
}

async function loadCandidatos() {
    const res = await fetch('/api/admin/candidatos');
    if (!res.ok) return;
    const candidatos = await res.json();

    const list = document.getElementById('candidatosList');
    list.innerHTML = candidatos.map(c => {
        const nome = escapeHtml(c.nome);
        const apelido = escapeHtml(c.apelido);
        const foto = escapeHtml(c.foto || '/static/img/placeholder.svg');
        return `
        <div class="card mb-2">
            <div class="candidato-admin-item">
                <img src="${foto}" alt="${nome}">
                <div class="flex-grow-1">
                    <strong>${nome}</strong> — ${apelido}
                    ${c.ativo ? '<span class="badge bg-success ms-1">Ativo</span>' : '<span class="badge badge-inativo ms-1">Inativo</span>'}
                </div>
                <button class="btn btn-sm btn-outline-secondary"
                        data-toggle-candidato="${c.id}"
                        data-next-ativo="${!c.ativo}">
                    ${c.ativo ? 'Desativar' : 'Ativar'}
                </button>
            </div>
        </div>
    `;
    }).join('');
}

// Event delegation em vez de onclick inline no HTML gerado: um
// Content-Security-Policy restritivo (script-src 'self', sem
// 'unsafe-inline') bloqueia atributos onclick= — handlers inline exigiriam
// afrouxar a CSP, o que reabriria parte do que a correção de XSS acabou de
// fechar. Um único listener no container resolve sem esse trade-off.
document.getElementById('candidatosList').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-toggle-candidato]');
    if (!btn) return;
    const id = btn.dataset.toggleCandidato;
    const nextAtivo = btn.dataset.nextAtivo === 'true';
    toggleCandidato(id, nextAtivo);
});

async function toggleCandidato(id, ativo) {
    const formData = new FormData();
    formData.append('ativo', ativo);
    await fetch(`/api/admin/candidatos/${id}`, {
        method: 'PUT',
        headers: csrfHeaders(),
        body: formData,
    });
    loadCandidatos();
    loadStats();
}

document.getElementById('candidatoForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData(form);

    const res = await fetch('/api/admin/candidatos', {
        method: 'POST',
        headers: csrfHeaders(),
        body: formData,
    });

    if (!res.ok) {
        const data = await res.json();
        alert(data.detail || 'Erro ao criar candidato');
        return;
    }

    form.reset();
    loadCandidatos();
    loadStats();
});

document.getElementById('btnSearch').addEventListener('click', async () => {
    const cpf = document.getElementById('searchCpf').value.replace(/\D/g, '');
    if (!cpf) return;

    const res = await fetch(`/api/admin/search?cpf=${cpf}`);
    const results = await res.json();

    const container = document.getElementById('searchResults');
    if (results.length === 0) {
        container.innerHTML = '<p class="text-muted">Nenhum resultado encontrado.</p>';
        return;
    }

    container.innerHTML = results.map(r => `
        <div class="card mb-2">
            <div class="card-body">
                <strong>${escapeHtml(r.nome)}</strong> — Sócio: ${escapeHtml(r.numero_socio)} — CPF: ${escapeHtml(r.cpf)}<br>
                <small class="text-muted">${escapeHtml(r.data_resposta)}</small><br>
                Candidatos: ${escapeHtml(r.candidatos.join(', '))}<br>
                Modalidades: ${escapeHtml(r.departamentos.join(', ') || '-')}${r.departamento_outros ? ` (${escapeHtml(r.departamento_outros)})` : ''}<br>
                Preferido: ${escapeHtml(r.preferido || '-')}
            </div>
        </div>
    `).join('');
});

// Checa res.ok ANTES de baixar. Sem isso, uma sessão expirada (401) faz o
// navegador salvar um "resultados.csv" com {"detail":"Not authenticated"}
// dentro — o download "funciona", o arquivo está errado, e nada na tela diz
// que houve falha. Falhar em silêncio num botão de exportação é pior do que
// falhar alto: quem baixou acha que tem os dados.
async function baixarExportacao(url, filename) {
    let res;
    try {
        res = await fetch(url);
    } catch {
        alert('Não foi possível falar com o servidor. Verifique a conexão.');
        return;
    }

    if (!res.ok) {
        alert(
            res.status === 401 || res.status === 403
                ? 'Sua sessão expirou. Entre novamente para exportar.'
                : `Falha ao exportar (HTTP ${res.status}).`
        );
        return;
    }

    downloadBlob(await res.blob(), filename);
}

function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

const EXPORTACOES = [
    ['exportCsv', '/api/admin/export/csv', 'respostas.csv'],
    ['exportExcel', '/api/admin/export/excel', 'respostas.xlsx'],
    ['exportResultadosCsv', '/api/admin/export/resultados/csv', 'resultados.csv'],
    ['exportResultadosExcel', '/api/admin/export/resultados/excel', 'resultados.xlsx'],
];

EXPORTACOES.forEach(([id, url, filename]) => {
    document.getElementById(id).addEventListener('click', (e) => {
        e.preventDefault();
        baixarExportacao(url, filename);
    });
});
