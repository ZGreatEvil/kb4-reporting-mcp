// chat page; served from /static so the page can run under a strict content security policy
(() => {
  lucide.createIcons();

  // give up only when nothing has arrived for this long; a long answer that keeps streaming is fine
  const CHAT_IDLE_TIMEOUT_MS = 180000;
  // same limits as the server (web/main.py)
  const MAX_MESSAGE_CHARS = 4000;
  const MAX_HISTORY_CHARS = 20000;
  const COUNTER_FROM = 3500;
  const HEALTH_EVERY_MS = 30000;

  const $ = (s) => document.querySelector(s);
  const chat = $('#chat');
  const form = $('#form');
  const input = $('#message');
  const send = $('#send');
  const newChat = $('#new-chat');
  const counter = $('#counter');
  const statusChip = $('#status');
  const picker = $('#lang-picker');
  const welcome = $('#welcome');

  // every piece of page text, per language; server messages come back already translated
  const STRINGS = {
    id: {
      welcome: 'Siap. Tanyakan tentang risk score, kampanye phishing, pengguna, grup, training atau panduan NIST. Saya juga bisa membuat grafik dan file CSV.',
      placeholder: 'Tanya laporan KnowBe4…',
      inputLabel: 'Pertanyaan Anda',
      send: 'Kirim',
      sendLabel: 'Kirim pertanyaan',
      newChat: 'Baru',
      newChatLabel: 'Mulai percakapan baru',
      footnote: 'Model AI lokal · data KnowBe4 tidak keluar dari komputer ini',
      langGroup: 'Bahasa',
      status: { checking: 'Memeriksa…', ok: 'Online', degraded: 'Terbatas', offline: 'Offline' },
      statusTitle: {
        checking: 'Memeriksa server…',
        ok: 'Semua layanan berjalan',
        degraded: 'Sebagian layanan bermasalah; jawaban bisa gagal. Admin: lihat /health',
        offline: 'Server tidak dapat dihubungi',
      },
      loading: (s) => `Menganalisis data KnowBe4… (${s} dtk)`,
      thinking: (s) => `Berpikir… (${s} dtk)`,
      tool: (name, s) => `Mengambil data: ${name}… (${s} dtk)`,
      noAnswer: 'Tidak ada respons yang diterima.',
      timeout: (s) => `Tidak ada respons selama ${s} detik. Coba pertanyaan yang lebih sempit.`,
      network: 'Tidak dapat terhubung ke server. Periksa apakah server sedang berjalan, lalu coba lagi.',
      tooLong: 'Pertanyaan atau percakapan terlalu panjang. Mulai percakapan baru atau persingkat pertanyaan.',
      server: (code) => `Server mengalami masalah (HTTP ${code}). Coba lagi sebentar lagi.`,
      replied: (s) => `Dijawab dalam ${s} dtk`,
      failed: (s) => `Gagal setelah ${s} dtk`,
      queued: 'Antre… menunggu jawaban sebelumnya',
      locale: 'id-ID',
    },
    en: {
      welcome: 'Ready. Ask about risk scores, phishing campaigns, users, groups, training or NIST guidance. I can also make charts and CSV files.',
      placeholder: 'Ask about KnowBe4 reports…',
      inputLabel: 'Your question',
      send: 'Send',
      sendLabel: 'Send question',
      newChat: 'New',
      newChatLabel: 'Start a new conversation',
      footnote: 'Local AI model · KnowBe4 data stays on this computer',
      langGroup: 'Language',
      status: { checking: 'Checking…', ok: 'Online', degraded: 'Limited', offline: 'Offline' },
      statusTitle: {
        checking: 'Checking the server…',
        ok: 'All services running',
        degraded: 'Some services have a problem; answers may fail. Admins: see /health',
        offline: 'The server cannot be reached',
      },
      loading: (s) => `Analysing KnowBe4 data… (${s} s)`,
      thinking: (s) => `Thinking… (${s} s)`,
      tool: (name, s) => `Fetching data: ${name}… (${s} s)`,
      noAnswer: 'No response received.',
      timeout: (s) => `No response for ${s} seconds. Try a narrower question.`,
      network: 'Cannot reach the server. Check that it is running, then try again.',
      tooLong: 'The question or conversation is too long. Start a new conversation or shorten the question.',
      server: (code) => `The server had a problem (HTTP ${code}). Try again in a moment.`,
      replied: (s) => `Replied in ${s} s`,
      failed: (s) => `Failed after ${s} s`,
      queued: 'Queued… waiting for the previous answer',
      locale: 'en-GB',
    },
  };
  const LANG_KEY = 'kb4-chat-language';
  let lang = null;
  let busy = false;
  let healthState = 'checking';
  // questions sent while an answer is still coming wait here and go out in order
  const queue = [];
  const MAX_QUEUE = 5;
  // this conversation only; sent with each question so "2" or "show more" make sense
  const history = [];
  const HISTORY_SENT = 6;
  // bumped by "new chat", so an answer still on its way is dropped
  let conversation = 0;
  let current = null;

  const touchScreen = () => window.matchMedia('(pointer: coarse)').matches;

  function updateControls() {
    send.disabled = !lang || queue.length >= MAX_QUEUE;
    newChat.disabled = !lang || (!busy && !chat.querySelector('.msg-user'));
  }

  // only follow new text when the reader was at the bottom before it arrived, so scrolling up to read
  // is not undone; checked before the change, since a long answer moves the bottom away
  const nearBottom = () => chat.scrollHeight - chat.scrollTop - chat.clientHeight < 80;
  const toBottom = (force = false) => { if (force || nearBottom()) chat.scrollTop = chat.scrollHeight; };
  function keepBottom(change) {
    const stick = nearBottom();
    change();
    if (stick) chat.scrollTop = chat.scrollHeight;
    return stick;
  }
  // charts load after the text; keep following them if the reader was following
  chat.addEventListener('load', (e) => {
    if (e.target.tagName === 'IMG' && chat.dataset.follow === '1') chat.scrollTop = chat.scrollHeight;
  }, true);
  chat.addEventListener('scroll', () => { chat.dataset.follow = nearBottom() ? '1' : '0'; }, { passive: true });

  // model output is untrusted html once rendered; it is cleaned as a string and parsed in an inert
  // <template>, so hostile markup never touches the live page. tables get a wrapper so they scroll
  function renderMarkdown(text) {
    const template = document.createElement('template');
    template.innerHTML = DOMPurify.sanitize(marked.parse(text));
    const fragment = template.content;
    // screen readers announce an image without alt by its file name
    fragment.querySelectorAll('img:not([alt])').forEach((img) => { img.alt = ''; });
    fragment.querySelectorAll('table').forEach((table) => {
      const wrap = document.createElement('div');
      wrap.className = 'table-wrap';
      wrap.tabIndex = 0;
      table.replaceWith(wrap);
      wrap.appendChild(table);
    });
    return fragment;
  }

  // storage can be blocked (private windows, strict settings); the picker then just shows again
  function savedLang() {
    try {
      const v = localStorage.getItem(LANG_KEY);
      return v === 'id' || v === 'en' ? v : null;
    } catch { return null; }
  }

  function showStatus() {
    const t = STRINGS[lang || 'id'];
    statusChip.dataset.state = healthState;
    $('#status-text').textContent = t.status[healthState];
    statusChip.title = t.statusTitle[healthState];
  }

  function applyLang(l) {
    lang = l;
    try { localStorage.setItem(LANG_KEY, l); } catch {}
    const t = STRINGS[l];
    document.documentElement.lang = l;
    $('#welcome-text').textContent = t.welcome;
    input.placeholder = t.placeholder;
    input.setAttribute('aria-label', t.inputLabel);
    $('#send-label').textContent = t.send;
    send.setAttribute('aria-label', t.sendLabel);
    $('#new-chat-label').textContent = t.newChat;
    newChat.setAttribute('aria-label', t.newChatLabel);
    newChat.title = t.newChatLabel;
    $('#footnote').textContent = t.footnote;
    $('#lang-switch').setAttribute('aria-label', t.langGroup);
    document.querySelectorAll('.lang-btn').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.lang === l)));
    picker.classList.add('hidden');
    welcome.classList.remove('hidden');
    input.disabled = false;
    showStatus();
    showCounter();
    updateControls();
  }

  document.querySelectorAll('.lang-btn, .pick-btn').forEach((b) => {
    b.addEventListener('click', () => {
      const fromPicker = b.classList.contains('pick-btn');
      applyLang(b.dataset.lang);
      if (fromPicker) input.focus();
    });
  });

  const initial = savedLang();
  if (initial) {
    applyLang(initial);
  } else {
    picker.classList.remove('hidden');
    // the picker above says what to do; a long placeholder here would wrap and clip on small phones
    input.placeholder = '';
    input.disabled = true;
    send.disabled = true;
    $('#send-label').textContent = '…';
    showStatus();
  }

  // header badge: is the bot actually able to answer?
  async function checkHealth() {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const r = await fetch('/health', { signal: controller.signal, cache: 'no-store' });
      const h = await r.json();
      healthState = h.status === 'ok' ? 'ok' : 'degraded';
      if (h.consoles && h.consoles.length) $('#consoles').textContent = h.consoles.map((c) => c.toUpperCase()).join(' · ');
    } catch {
      healthState = 'offline';
    } finally {
      clearTimeout(timer);
      showStatus();
    }
  }
  checkHealth();
  setInterval(checkHealth, HEALTH_EVERY_MS);

  function showCounter() {
    const n = input.value.length;
    counter.classList.toggle('hidden', n < COUNTER_FROM);
    if (n >= COUNTER_FROM) {
      const fmt = new Intl.NumberFormat(STRINGS[lang || 'id'].locale);
      counter.textContent = `${fmt.format(n)} / ${fmt.format(MAX_MESSAGE_CHARS)}`;
    }
  }

  function resizeInput() {
    input.style.height = '';
    if (input.value) input.style.height = input.scrollHeight + 'px';
    // a scrollbar only once the text is taller than the box can grow (max-h-32 = 128px)
    input.style.overflowY = input.scrollHeight > 128 ? 'auto' : 'hidden';
  }

  input.addEventListener('input', () => { resizeInput(); showCounter(); });

  // Enter sends, Shift+Enter is a new line; never while an IME is still composing a word
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  function add(content, cls, isMarkdown = false) {
    const isUser = cls === 'user';
    const wrapper = document.createElement('div');
    wrapper.className = isUser ? 'msg-user' : 'msg-ai';
    const bubble = document.createElement('div');
    if (isUser) {
      bubble.className = 'bubble-user';
      bubble.textContent = content;
      wrapper.appendChild(bubble);
    } else {
      wrapper.innerHTML = '<div class="avatar" aria-hidden="true"><i data-lucide="bot" class="w-4 h-4"></i></div>';
      bubble.className = 'bubble-ai flex-1 p-4 text-sm leading-relaxed prose-ai';
      if (isMarkdown) bubble.replaceChildren(renderMarkdown(content));
      else bubble.textContent = content;
      wrapper.appendChild(bubble);
    }
    chat.appendChild(wrapper);
    lucide.createIcons();
    toBottom(true);
    return bubble;
  }

  newChat.addEventListener('click', () => {
    conversation += 1;
    queue.length = 0;
    history.length = 0;
    if (current) current.abort();
    chat.querySelectorAll('.msg-user, .msg-ai:not(#welcome)').forEach((el) => el.remove());
    input.value = '';
    resizeInput();
    showCounter();
    updateControls();
    input.focus();
  });

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const m = input.value.trim().slice(0, MAX_MESSAGE_CHARS);
    if (!m || !lang || queue.length >= MAX_QUEUE) return;
    input.value = '';
    resizeInput();
    showCounter();
    const userBubble = add(m, 'user');
    const item = { m, lang, tag: null, conversation };
    if (busy) {
      item.tag = document.createElement('div');
      item.tag.className = 'queued-tag mt-1 text-[11px] text-white/90';
      item.tag.textContent = STRINGS[lang].queued;
      userBubble.appendChild(item.tag);
    }
    queue.push(item);
    updateControls();
    if (!busy) drain();
  });

  async function drain() {
    busy = true;
    updateControls();
    while (queue.length) {
      const item = queue.shift();
      if (item.tag) item.tag.remove();
      updateControls();
      if (item.conversation === conversation) await runQuestion(item.m, item.lang);
    }
    busy = false;
    updateControls();
    // on phones focusing would pop the keyboard up after every answer
    if (!touchScreen()) input.focus();
  }

  function remember(question, note, answer) {
    // the note (what was fetched, which page) goes first so it survives when long answers are cut
    let content = (note ? note + '\n\n' : '') + answer;
    if (content.length > MAX_HISTORY_CHARS) content = content.slice(0, MAX_HISTORY_CHARS);
    history.push({ role: 'user', content: question }, { role: 'assistant', content });
  }

  async function runQuestion(m, requestLang) {
    // the language at the time of asking, even if the switch changes while it waits
    const t = STRINGS[requestLang];
    const asked = conversation;

    // status line with elapsed time until text arrives, since local answers can take a while
    const bubble = add(t.loading(0), 'ai', false);
    bubble.setAttribute('aria-busy', 'true');
    const started = Date.now();
    const secs = () => Math.round((Date.now() - started) / 1000);
    let status = (s) => t.loading(s);
    let text = '';
    const showProgress = () => { if (!text) bubble.textContent = status(secs()); };
    const ticker = setInterval(showProgress, 1000);

    const controller = new AbortController();
    current = controller;
    let idle;
    let timedOut = false;
    const touch = () => {
      clearTimeout(idle);
      idle = setTimeout(() => { timedOut = true; controller.abort(); }, CHAT_IDLE_TIMEOUT_MS);
    };
    let failed = false;
    const showError = (message) => {
      failed = true;
      const span = document.createElement('span');
      span.className = 'text-rose-600 dark:text-rose-400 font-medium';
      span.textContent = '⚠️ ' + message;
      bubble.replaceChildren(span);
    };
    let finished = false;
    // re-rendering markdown on every chunk froze the page on long answers; ~10 renders a second is plenty
    let renderTimer = null;
    const renderNow = () => {
      renderTimer = null;
      chat.dataset.follow = keepBottom(() => bubble.replaceChildren(renderMarkdown(text))) ? '1' : '0';
    };
    const scheduleRender = () => { if (!renderTimer) renderTimer = setTimeout(renderNow, 100); };

    const handle = (ev) => {
      if (ev.type === 'thinking') { status = t.thinking; showProgress(); }
      else if (ev.type === 'tool') { status = (s) => t.tool(ev.name, s); showProgress(); }
      else if (ev.type === 'delta') { text += ev.text; scheduleRender(); }
      else if (ev.type === 'reset') { clearTimeout(renderTimer); renderTimer = null; text = ''; showProgress(); }
      else if (ev.type === 'done') {
        clearTimeout(renderTimer); finished = true; text = ev.answer || t.noAnswer; renderNow();
        if (ev.answer) remember(m, ev.note, ev.answer);
      }
      else if (ev.type === 'error') { clearTimeout(renderTimer); finished = true; showError(ev.message); }
      toBottom();
    };

    try {
      touch();
      const r = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: m, language: requestLang, history: history.slice(-HISTORY_SENT) }),
        signal: controller.signal,
      });
      if (!r.ok) {
        showError(r.status === 422 ? t.tooLong : t.server(r.status));
        return;
      }

      // one json event per line; a chunk can end mid-line
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        touch();
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) if (line.trim()) handle(JSON.parse(line));
      }
      if (buffer.trim()) handle(JSON.parse(buffer));
      if (!finished) { clearTimeout(renderTimer); showError(t.noAnswer); }
    } catch (err) {
      clearTimeout(renderTimer);
      // "new chat" aborts on purpose; that bubble is already gone
      if (asked !== conversation) return;
      if (timedOut) showError(t.timeout(CHAT_IDLE_TIMEOUT_MS / 1000));
      else if (err instanceof SyntaxError) showError(t.noAnswer);
      else showError(t.network);
    } finally {
      clearInterval(ticker);
      clearTimeout(idle);
      if (current === controller) current = null;
      const took = document.createElement('div');
      took.className = 'reply-time';
      took.textContent = (failed ? t.failed : t.replied)(secs());
      keepBottom(() => bubble.appendChild(took));
      bubble.setAttribute('aria-busy', 'false');
    }
  }
})();
