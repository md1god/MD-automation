const fs = require('fs');
const path = require('path');

const LIBRARY_DIR = 'content-library';
const STATE_FILE = 'build-state.json';
const INDEX_FILE = 'pages-index.json';
const PAGES_DIR = 'pages';

function readJsonSafe(file, fallback) {
  if (!fs.existsSync(file)) return fallback;
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (err) {
    console.error(`⚠️ خطأ في قراءة ${file}: ${err.message}`);
    return fallback;
  }
}

function writeJsonSafe(file, data) {
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2), 'utf8');
  fs.renameSync(tmp, file);
}

function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

if (!fs.existsSync(LIBRARY_DIR)) {
  console.error(`❌ مجلد ${LIBRARY_DIR} غير موجود. تم إيقاف التنفيذ.`);
  process.exit(1);
}

const files = fs.readdirSync(LIBRARY_DIR).filter(f => f.endsWith('.json'));
if (files.length === 0) {
  console.error(`❌ لا توجد ملفات محتوى في ${LIBRARY_DIR}. تم إيقاف التنفيذ.`);
  process.exit(1);
}

const library = files.map(f => {
  const item = readJsonSafe(path.join(LIBRARY_DIR, f), null);
  return item ? { ...item, id: f.replace('.json', '') } : null;
}).filter(Boolean);

let state = readJsonSafe(STATE_FILE, {
  pageCount: 0,
  queue: [],
  lastUsedId: null,
  lastUpdate: null
});

if (!state.queue || state.queue.length === 0) {
  let newQueue = shuffle(library.map(item => item.id));
  if (state.lastUsedId && newQueue[0] === state.lastUsedId && newQueue.length > 1) {
    [newQueue[0], newQueue[1]] = [newQueue[1], newQueue[0]];
  }
  state.queue = newQueue;
  console.log('🔄 المكتبة كلها استخدمت — بدء دورة جديدة مخلوطة.');
}

const nextId = state.queue.shift();
const item = library.find(i => i.id === nextId);

if (!item) {
  console.error(`❌ العنصر ${nextId} غير موجود. تم إيقاف التنفيذ.`);
  process.exit(1);
}

if (!fs.existsSync(PAGES_DIR)) fs.mkdirSync(PAGES_DIR, { recursive: true });

state.pageCount++;
const slug = `page-${String(state.pageCount).padStart(4, '0')}`;
const pagePath = path.join(PAGES_DIR, `${slug}.html`);
const now = new Date();

const fragment = `<article class="generated-page" id="${slug}" data-title="${item.title}" data-image="${item.image}" data-audio="${item.audio}">
  <h2>${item.title}</h2>
  <p>${item.description}</p>
  <button class="cta-button" type="button">${item.cta}</button>
  <meta name="page-date" content="${now.toISOString()}">
</article>`;

fs.writeFileSync(pagePath, fragment, 'utf8');

let index = readJsonSafe(INDEX_FILE, []);
index.push({
  id: slug,
  title: item.title,
  image: item.image,
  audio: item.audio,
  date: now.toISOString(),
  file: `pages/${slug}.html`
});
writeJsonSafe(INDEX_FILE, index);

state.lastUsedId = nextId;
state.lastUpdate = now.toISOString();
writeJsonSafe(STATE_FILE, state);

console.log(`✅ تم إنشاء ${slug}.html — "${item.title}"`);
console.log(`📊 الصفحة رقم ${state.pageCount} | متبقي في الدورة: ${state.queue.length}`);