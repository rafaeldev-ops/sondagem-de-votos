/* Sondagem Clube - Frontend Application */

const state = {
    step: 1,
    sessionToken: null,
    telefone: null,
    candidatos: [],
    selectedIds: new Set(),
    // Ponto focal: um só, então é um id e não um Set. null = ainda não
    // escolhido, que é o estado com que a etapa 4 começa.
    preferidoId: null,
    resendInterval: null,
    departamentos: [],
    selectedDepartamentoIds: new Set(),
};

// Limite de seleção do desenho aprovado ("máximo 20"). Também reforçado no
// backend (VotoRequest.candidatos_ids, max_length=20) — o limite aqui é só
// para dar feedback imediato ao usuário, nunca a única barreira.
const MAX_CANDIDATOS = 20;

// Defesa em profundidade: mesmo com sanitização no backend, nunca interpole
// texto vindo da API direto em innerHTML sem escapar. Isso evita XSS mesmo
// se algum dado não sanitizado chegar até aqui por qualquer outro caminho.
function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value ?? '';
    return div.innerHTML;
}

// Duas letras a partir do primeiro e do último nome ("Carlos Eduardo Silva"
// -> "CS"). Nome de uma palavra só devolve uma letra, e nome vazio devolve
// "?" em vez de string vazia — um círculo colorido em branco pareceria falha
// de carregamento.
function iniciais(nome) {
    const partes = (nome || '').trim().split(/\s+/).filter(Boolean);
    if (partes.length === 0) return '?';
    const primeira = partes[0][0];
    const ultima = partes.length > 1 ? partes[partes.length - 1][0] : '';
    return (primeira + ultima).toUpperCase();
}

// Cor do avatar derivada do id: o mesmo candidato tem sempre a mesma cor, em
// qualquer aparelho e em qualquer recarga. Se viesse de random, a lista
// trocaria de cor a cada visita e a cor deixaria de servir como ponto de
// referência para achar um nome.
const AVATAR_CORES = 6;

function corDoAvatar(id) {
    return `c${Math.abs(Number(id) || 0) % AVATAR_CORES}`;
}

const steps = ['step1', 'step2', 'step3', 'step4', 'step5', 'step6', 'stepThanks'];
const stepLabels = [
    'Etapa 1 de 6 — Cadastro',
    'Etapa 2 de 6 — Verificação',
    'Etapa 3 de 6 — Candidatos',
    'Etapa 4 de 6 — Ponto focal',
    'Etapa 5 de 6 — Modalidades',
    'Etapa 6 de 6 — Consentimento',
];

function showToast(message) {
    const toast = document.getElementById('alertToast');
    document.getElementById('toastMessage').textContent = message;
    bootstrap.Toast.getOrCreateInstance(toast).show();
}

// Uma bolinha por etapa. Concluída vira check, atual fica em destaque
// esperando ser confirmada, futura fica apagada.
//
// Só troca de CLASSE, nunca element.style: a CSP do projeto não tem
// 'unsafe-inline' em style-src (a barra de progresso anterior escapava
// disso por ser CSSOM, mas classe é mais simples e não depende dessa
// distinção). Ver app/middlewares/security_headers.py.
function renderStepDots(n) {
    document.querySelectorAll('#stepDots .step-dot').forEach((dot) => {
        const etapa = Number(dot.dataset.step);
        // n > stepLabels.length é a tela de agradecimento: aí as cinco
        // etapas estão concluídas e nenhuma é a atual.
        const concluida = etapa < n;
        const atual = etapa === n;

        dot.classList.toggle('is-done', concluida);
        dot.classList.toggle('is-current', atual);

        if (atual) {
            dot.setAttribute('aria-current', 'step');
        } else {
            dot.removeAttribute('aria-current');
        }
    });
}

function goToStep(n) {
    state.step = n;
    steps.forEach((id, i) => {
        document.getElementById(id).classList.toggle('d-none', i !== n - 1);
    });

    renderStepDots(n);

    // Derivado de stepLabels.length, não cravado: o 4 e o 25 anteriores eram
    // a mesma informação escrita duas vezes, e ambos ficavam errados assim
    // que uma etapa era acrescentada.
    if (n <= stepLabels.length) {
        document.getElementById('stepLabel').textContent = stepLabels[n - 1];
    } else {
        document.getElementById('stepLabel').textContent = 'Participação concluída';
    }
}

function formatCPF(value) {
    const digits = value.replace(/\D/g, '').slice(0, 11);
    return digits
        .replace(/(\d{3})(\d)/, '$1.$2')
        .replace(/(\d{3})(\d)/, '$1.$2')
        .replace(/(\d{3})(\d{1,2})$/, '$1-$2');
}

function formatPhone(value) {
    const digits = value.replace(/\D/g, '').slice(0, 11);
    if (digits.length <= 10) {
        return digits.replace(/(\d{2})(\d{4})(\d{0,4})/, '($1) $2-$3').trim();
    }
    return digits.replace(/(\d{2})(\d{5})(\d{0,4})/, '($1) $2-$3').trim();
}

function normalizeCPF(value) {
    return value.replace(/\D/g, '');
}

function normalizePhone(value) {
    return value.replace(/\D/g, '');
}

// Exibe o celular parcialmente mascarado na tela de OTP — ex: "(11) 9**-1234".
// Nunca mostrar o número completo de volta na tela, mesmo sendo o próprio
// número do usuário: reduz o que fica visível por cima do ombro (shoulder
// surfing) em dispositivo compartilhado ou print de tela.
function maskPhoneDisplay(digits) {
    const ddd = digits.slice(0, 2);
    const subscriber = digits.slice(2);
    const first = subscriber.slice(0, 1);
    const last4 = subscriber.slice(-4);
    return `(${ddd}) ${first}**-${last4}`;
}

async function validateCPFRemote(cpf) {
    const res = await fetch('/api/survey/validate-cpf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cpf: normalizeCPF(cpf) }),
    });
    return res.json();
}

async function getRecaptchaToken() {
    const siteKey = document.body.dataset.recaptchaSiteKey;
    if (!siteKey || typeof grecaptcha === 'undefined') {
        // Sem site key configurada: manda string vazia. O backend decide o
        // que fazer com isso (falha fechado fora de DEBUG=true — ver
        // app/integrations/recaptcha.py). Antes deste fix, aqui era enviado
        // o literal 'dev-bypass', que funcionava como senha mestra pública
        // porque estava neste mesmo arquivo, servido a qualquer visitante.
        return '';
    }
    return grecaptcha.execute(siteKey, { action: 'register' });
}

// CPF input validation
const cpfInput = document.getElementById('cpf');
let cpfValid = false;

cpfInput.addEventListener('input', (e) => {
    e.target.value = formatCPF(e.target.value);
    cpfInput.classList.remove('is-valid', 'is-invalid');
    cpfValid = false;
});

cpfInput.addEventListener('blur', async () => {
    const cpf = normalizeCPF(cpfInput.value);
    if (cpf.length !== 11) return;

    try {
        const result = await validateCPFRemote(cpf);
        if (!result.valid || !result.available) {
            cpfInput.classList.add('is-invalid');
            cpfInput.classList.remove('is-valid');
            document.getElementById('cpfFeedback').textContent =
                result.message || 'CPF inválido';
            cpfValid = false;
        } else {
            cpfInput.classList.add('is-valid');
            cpfInput.classList.remove('is-invalid');
            cpfValid = true;
        }
    } catch {
        cpfInput.classList.add('is-invalid');
        document.getElementById('cpfFeedback').textContent = 'Erro ao validar CPF';
    }
});

document.getElementById('telefone').addEventListener('input', (e) => {
    e.target.value = formatPhone(e.target.value);
});

document.getElementById('numeroSocio').addEventListener('input', (e) => {
    e.target.value = e.target.value.replace(/\D/g, '').slice(0, 4);
});

// Destaque do cartão "sou titular do grupo". O CSS também cobre isso via
// :has(input:checked), mas WebView de Android antigo não implementa :has() —
// a classe aqui é quem garante o retorno visual em todo aparelho.
const titularCheck = document.getElementById('titular');
titularCheck.addEventListener('change', () => {
    titularCheck.closest('.choice-card').classList.toggle('selected', titularCheck.checked);
});

// Estado inicial das bolinhas: etapa 1 é a atual. goToStep() cuida daqui em
// diante, mas ele só roda quando o usuário avança.
renderStepDots(state.step);

// Step 1: Registration
document.getElementById('cadastroForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!cpfValid) {
        showToast('Verifique o CPF antes de continuar');
        return;
    }

    const numeroSocio = document.getElementById('numeroSocio').value;
    if (!/^[0-9]{4}$/.test(numeroSocio)) {
        showToast('Informe os 4 dígitos do seu número de sócio');
        return;
    }

    const btn = document.getElementById('btnCadastro');
    btn.disabled = true;

    try {
        const recaptchaToken = await getRecaptchaToken();
        const res = await fetch('/api/survey/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                nome: document.getElementById('nome').value.trim(),
                cpf: normalizeCPF(cpfInput.value),
                numero_socio: numeroSocio,
                // Sempre o estado real do checkbox: desmarcado é a resposta
                // "não sou titular", não ausência de resposta. O backend
                // exige o campo (CadastroRequest.titular não tem default).
                titular: titularCheck.checked,
                telefone: normalizePhone(document.getElementById('telefone').value),
                recaptcha_token: recaptchaToken,
            }),
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Erro no cadastro');

        state.sessionToken = data.session_token;
        state.telefone = normalizePhone(document.getElementById('telefone').value);
        document.getElementById('phoneDisplay').textContent = maskPhoneDisplay(state.telefone);
        goToStep(2);
        startResendTimer();
    } catch (err) {
        showToast(err.message);
    } finally {
        btn.disabled = false;
    }
});

// OTP digit inputs
const otpDigits = document.querySelectorAll('.otp-digit');
otpDigits.forEach((input, idx) => {
    input.addEventListener('input', (e) => {
        e.target.value = e.target.value.replace(/\D/g, '').slice(0, 1);
        if (e.target.value && idx < otpDigits.length - 1) {
            otpDigits[idx + 1].focus();
        }
    });
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Backspace' && !e.target.value && idx > 0) {
            otpDigits[idx - 1].focus();
        }
    });
});

function getOTPCode() {
    return Array.from(otpDigits).map(i => i.value).join('');
}

function startResendTimer() {
    let seconds = 60;
    const btn = document.getElementById('btnResend');
    const timer = document.getElementById('resendTimer');
    btn.disabled = true;

    if (state.resendInterval) clearInterval(state.resendInterval);

    state.resendInterval = setInterval(() => {
        seconds--;
        timer.textContent = seconds;
        if (seconds <= 0) {
            clearInterval(state.resendInterval);
            btn.disabled = false;
            timer.textContent = '0';
        }
    }, 1000);
}

document.getElementById('otpForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const code = getOTPCode();
    if (code.length !== 6) {
        showToast('Digite o código completo');
        return;
    }

    try {
        const res = await fetch('/api/survey/verify-otp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                telefone: state.telefone,
                codigo: code,
                session_token: state.sessionToken,
            }),
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Código inválido');

        await loadCandidatos();
        await loadDepartamentos();
        goToStep(3);
    } catch (err) {
        document.getElementById('otpFeedback').textContent = err.message;
        showToast(err.message);
    }
});

document.getElementById('btnResend').addEventListener('click', async () => {
    try {
        const res = await fetch('/api/survey/resend-otp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                telefone: state.telefone,
                session_token: state.sessionToken,
            }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        startResendTimer();
        otpDigits.forEach(i => i.value = '');
        otpDigits[0].focus();
    } catch (err) {
        showToast(err.message);
    }
});

async function loadCandidatos() {
    const res = await fetch('/api/survey/candidatos');
    state.candidatos = await res.json();

    document.getElementById('maxCandidatos').textContent = MAX_CANDIDATOS;

    const grid = document.getElementById('candidatosGrid');
    grid.innerHTML = '';

    state.candidatos.forEach(c => {
        const nome = escapeHtml(c.nome);
        const apelido = escapeHtml(c.apelido);
        const foto = escapeHtml(c.foto);

        const card = document.createElement('div');
        card.className = 'candidato-card';
        card.dataset.id = c.id;
        card.innerHTML = `
            ${c.foto
                ? `<img class="candidato-avatar" src="${foto}" alt="${nome}" loading="lazy">`
                : `<div class="candidato-avatar-placeholder ${corDoAvatar(c.id)}" aria-hidden="true">${escapeHtml(iniciais(c.nome))}</div>`}
            <div class="candidato-info">
                <div class="candidato-apelido">${apelido}</div>
                <div class="candidato-nome">${nome}</div>
            </div>
            <input class="form-check-input" type="checkbox" id="cand-${c.id}" value="${c.id}" aria-label="Selecionar ${nome}">`;
        grid.appendChild(card);
    });

    grid.querySelectorAll('.candidato-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (e.target.tagName === 'INPUT') return;
            const cb = card.querySelector('input[type=checkbox]');
            cb.checked = !cb.checked;
            cb.dispatchEvent(new Event('change'));
        });
    });

    grid.querySelectorAll('input[type=checkbox]').forEach(cb => {
        cb.addEventListener('change', () => {
            const id = parseInt(cb.value);
            const card = cb.closest('.candidato-card');

            if (cb.checked && state.selectedIds.size >= MAX_CANDIDATOS) {
                cb.checked = false;
                showToast(`Você pode selecionar no máximo ${MAX_CANDIDATOS} candidatos`);
                return;
            }

            if (cb.checked) {
                state.selectedIds.add(id);
                card.classList.add('selected');
            } else {
                state.selectedIds.delete(id);
                card.classList.remove('selected');
            }
            updateCandidatosCount();
        });
    });

    updateCandidatosCount();
}

// Contador "Selecionados X/20" no topo da lista. Lê o tamanho do Set, e não
// um acumulador próprio: o caminho do limite atingido devolve o checkbox
// para desmarcado sem mexer no Set, e um contador incrementado à mão sairia
// de sincronia justamente aí.
function updateCandidatosCount() {
    document.getElementById('candidatosCount').textContent = state.selectedIds.size;
}

// Etapa 4: os mesmos cartões da etapa 3, só que com escolha única e
// listando APENAS quem foi marcado antes. Oferecer a lista inteira deixaria
// escolher alguém em quem a pessoa não votou — o backend recusa isso ("o
// candidato preferencial deve estar entre os selecionados"), o que viraria
// erro no fim do fluxo em vez de opção que nunca aparece.
//
// O controle é checkbox, igual ao da etapa 3, mas a escolha é ÚNICA: marcar
// um desmarca o outro. O navegador não faz isso sozinho com checkbox (é o
// que o radio daria de graça), então a exclusividade é imposta aqui no
// handler de change — que dispara tanto pelo toque quanto pelo teclado
// (Tab + Espaço), fechando os dois caminhos.
//
// Marcar o que já estava marcado desmarca e zera a escolha, em vez de
// travar em "sempre há um selecionado": o botão CONTINUAR cobra a escolha,
// então dá para desfazer sem ficar preso.
function renderFocal() {
    const lista = document.getElementById('focalLista');

    // Reconstruído a cada entrada na etapa: dá para voltar e mudar a
    // seleção da etapa 3, e a lista precisa acompanhar. Como innerHTML
    // descarta os elementos antigos junto com os listeners, não há acúmulo.
    lista.innerHTML = '';

    const escolhidos = state.candidatos.filter(c => state.selectedIds.has(c.id));

    // Se o ponto focal escolhido antes foi desmarcado na etapa 3, ele deixa
    // de ser uma opção válida e a escolha precisa ser refeita.
    if (state.preferidoId !== null && !state.selectedIds.has(state.preferidoId)) {
        state.preferidoId = null;
    }

    escolhidos.forEach(c => {
        const nome = escapeHtml(c.nome);
        const apelido = escapeHtml(c.apelido);
        const foto = escapeHtml(c.foto);
        const marcado = state.preferidoId === c.id;

        const card = document.createElement('div');
        card.className = marcado ? 'candidato-card selected' : 'candidato-card';
        card.dataset.id = c.id;
        card.innerHTML = `
            ${c.foto
                ? `<img class="candidato-avatar" src="${foto}" alt="${nome}" loading="lazy">`
                : `<div class="candidato-avatar-placeholder ${corDoAvatar(c.id)}" aria-hidden="true">${escapeHtml(iniciais(c.nome))}</div>`}
            <div class="candidato-info">
                <div class="candidato-apelido">${apelido}</div>
                <div class="candidato-nome">${nome}</div>
            </div>
            <input class="form-check-input" type="checkbox" id="focal-${c.id}" value="${c.id}" aria-label="Escolher ${nome} como ponto focal"${marcado ? ' checked' : ''}>`;
        lista.appendChild(card);
    });

    lista.querySelectorAll('.candidato-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (e.target.tagName === 'INPUT') return;
            const cb = card.querySelector('input[type=checkbox]');
            cb.checked = !cb.checked;
            cb.dispatchEvent(new Event('change'));
        });
    });

    lista.querySelectorAll('input[type=checkbox]').forEach(cb => {
        cb.addEventListener('change', () => {
            state.preferidoId = cb.checked ? parseInt(cb.value) : null;
            // Uma passada só resolve os dois efeitos da escolha única:
            // desmarca todos os outros checkboxes (o navegador não faz isso
            // entre checkboxes) e acerta o destaque de cada cartão.
            lista.querySelectorAll('.candidato-card').forEach(outro => {
                const ehOEscolhido = Number(outro.dataset.id) === state.preferidoId;
                outro.querySelector('input[type=checkbox]').checked = ehOEscolhido;
                outro.classList.toggle('selected', ehOEscolhido);
            });
        });
    });
}

document.getElementById('btnCandidatos').addEventListener('click', () => {
    if (state.selectedIds.size === 0) {
        showToast('Selecione ao menos um candidato');
        return;
    }
    renderFocal();
    goToStep(4);
});

document.getElementById('btnFocal').addEventListener('click', () => {
    if (state.preferidoId === null) {
        showToast('Escolha quem será seu ponto focal no grupo');
        return;
    }
    goToStep(5);
});

async function loadDepartamentos() {
    const res = await fetch('/api/survey/departamentos');
    state.departamentos = await res.json();
    renderDepartamentos();
}

function renderDepartamentos() {
    const lista = document.getElementById('departamentosLista');
    lista.innerHTML = state.departamentos.map(d => `
        <div class="departamento-item" data-id="${d.id}">
            <input class="form-check-input mt-0" type="checkbox" id="dep-${d.id}">
            <label class="form-check-label flex-grow-1" for="dep-${d.id}">${escapeHtml(d.nome)}</label>
        </div>`).join('');

    lista.querySelectorAll('.departamento-item').forEach(item => {
        const id = Number(item.dataset.id);
        const check = item.querySelector('input');
        // Escuta "change" no checkbox, não "click" na linha: o <label for>
        // associa o texto ao checkbox, então clicar no nome dispara um
        // click na linha (que alternaria checked manualmente aqui) e, em
        // seguida, a ativação nativa do label encaminha um click sintético
        // para o checkbox — cujo próprio passo de pré-ativação alterna
        // checked de novo, desfazendo a primeira alternância. Resultado
        // líquido: clicar no nome não fazia nada. "change" dispara uma
        // única vez, venha o toggle do clique no label, no próprio
        // checkbox ou do teclado (Tab+Espaço), então não há esse zerar
        // duplicado. Os listeners são recriados a cada renderDepartamentos()
        // porque lista.innerHTML descarta os elementos antigos (e seus
        // listeners) junto — não há acúmulo em re-render.
        check.addEventListener('change', () => {
            item.classList.toggle('selected', check.checked);
            if (check.checked) {
                state.selectedDepartamentoIds.add(id);
            } else {
                state.selectedDepartamentoIds.delete(id);
            }
            updateDepartamentosUI();
        });
    });
}

function updateDepartamentosUI() {
    document.getElementById('departamentosCount').textContent =
        state.selectedDepartamentoIds.size;

    // "Outros" é reconhecido pelo nome só no cliente, para revelar o campo.
    // A obrigatoriedade de verdade é do servidor, que usa a coluna
    // exige_texto — se o nome mudar, o pior caso aqui é o campo não
    // aparecer e o backend recusar com a mensagem correta.
    const outros = state.departamentos.find(d => d.nome === 'Outros');
    const marcado = outros && state.selectedDepartamentoIds.has(outros.id);
    document.getElementById('departamentoOutrosWrap').classList.toggle('d-none', !marcado);
}

// Sócio digita sem acento no teclado do celular na maioria das vezes
// ("natacao", "judo", "hidroginastica"), então a busca precisa comparar sem
// acento dos dois lados — senão metade da lista some da busca mesmo
// existindo.
const semAcento = (s) => s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();

document.getElementById('departamentosBusca').addEventListener('input', (e) => {
    const q = semAcento(e.target.value);
    document.querySelectorAll('.departamento-item').forEach(item => {
        const nome = semAcento(item.querySelector('label').textContent);
        item.classList.toggle('d-none', !nome.includes(q));
    });
});

document.getElementById('btnDepartamentos').addEventListener('click', () => {
    if (state.selectedDepartamentoIds.size === 0) {
        showToast('Marque ao menos uma modalidade');
        return;
    }
    const wrap = document.getElementById('departamentoOutrosWrap');
    const texto = document.getElementById('departamentoOutros').value.trim();
    if (!wrap.classList.contains('d-none') && !texto) {
        showToast('Descreva qual modalidade em Outros');
        return;
    }
    goToStep(6);
});

document.getElementById('btnSubmit').addEventListener('click', async () => {
    const btn = document.getElementById('btnSubmit');
    // Opt-in de contato, não condição para participar — o botão segue sem
    // exigir o checkbox marcado. O valor enviado ao backend é sempre o
    // estado real do checkbox no momento do clique.
    const lgpdChecked = document.getElementById('lgpdCheck').checked;

    btn.disabled = true;

    try {
        const res = await fetch('/api/survey/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_token: state.sessionToken,
                candidatos_ids: Array.from(state.selectedIds),
                candidato_preferido_id: state.preferidoId,
                aceite_lgpd: lgpdChecked,
                departamentos_ids: [...state.selectedDepartamentoIds],
                departamento_outros: document.getElementById('departamentoOutros').value.trim(),
            }),
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);

        // steps tem 7 posições (…, step6, stepThanks) desde que o ponto
        // focal virou etapa própria; stepThanks é a sétima.
        goToStep(7);
    } catch (err) {
        showToast(err.message);
        btn.disabled = false;
    }
});
