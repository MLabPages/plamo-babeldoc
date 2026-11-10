// Exercise the actual app speech controller with deterministic browser callbacks.
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const app = readFileSync(join(__dirname, '../paperapp/static/app.js'), 'utf8');
const source = app.slice(app.indexOf('const synth = window.speechSynthesis;'), app.indexOf('// ---------------- 起動'));

function setup(texts = ['最初の文。次の文。', '次の段落。']) {
  const nodes = new Map(), timers = [], spoken = [], notices = [];
  let current;
  function node(textContent = '', i = 0) {
    const classes = new Set();
    return {textContent, dataset: {i: String(i)}, innerHTML: '', value: '',
      classList: {add: c => classes.add(c), remove: c => classes.delete(c)},
      scrollIntoView() {}, addEventListener() {}};
  }
  const paragraphs = texts.map(node);
  const synth = {getVoices: () => [], speak: u => spoken.push(u), cancel() {}};
  const context = {window: {speechSynthesis: synth}, SpeechSynthesisUtterance: function(text) { this.text = text; },
    $: s => { if (!nodes.has(s)) nodes.set(s, node()); return nodes.get(s); },
    prefs: {rate: 1, voice: ''}, cur: {id: 'paper', engine: 'local'},
    units: () => paragraphs, article: {querySelectorAll: () => paragraphs, querySelector: () => current},
    setCurrent: el => { current = el; }, savePos() {}, savePrefs() {}, applyPrefs() {}, stepPara() {}, esc: s => s,
    toast: s => notices.push(s), setTimeout: fn => timers.push(fn)};
  vm.createContext(context);
  vm.runInContext(source + '\nglobalThis.controller = {tts, ttsStart, ttsStop, ttsToggle, sentences};', context);
  return {...context.controller, synth, spoken, notices, nodes, context,
    flush() { while (timers.length) timers.shift()(); }};
}

test('error preserves unfinished sentence and resume repeats it', () => {
  const s = setup(); s.ttsStart(0); s.flush();
  const first = s.spoken[0]; first.onerror({error: 'network'});
  assert.equal(s.spoken.length, 1);
  assert.equal(s.tts.playing, false);
  assert.equal(s.nodes.get('#ttsPlay').textContent, '▶ 再開');
  s.ttsToggle(); s.flush();
  assert.equal(s.spoken[1].text, first.text);
  s.spoken[1].onend();
  assert.equal(s.spoken[2].text, '次の文。');
});
test('duplicate and stale callbacks do not skip sentences', () => {
  const s = setup(); s.ttsStart(0); s.flush();
  const first = s.spoken[0]; first.onend(); first.onend(); first.onerror({error: 'network'});
  assert.equal(s.spoken.length, 2);
  assert.equal(s.tts.playing, true);
  s.spoken[1].onend();
  assert.equal(s.spoken[2].text, '次の段落。');
});
test('manual stop resumes current chunk instead of whole paragraph', () => {
  const s = setup(); s.ttsStart(0); s.flush(); s.spoken[0].onend();
  s.ttsToggle(); s.ttsToggle(); s.flush();
  assert.equal(s.spoken[2].text, '次の文。');
});
test('synchronous cancel callbacks cannot advance old playback', () => {
  const s = setup(); s.ttsStart(0); s.flush();
  s.synth.cancel = () => s.spoken[0].onend();
  s.ttsStart(1); s.flush();
  assert.deepEqual(s.spoken.map(u => u.text), ['最初の文。', '次の段落。']);
});
test('rate/voice restart preserves pending chunk', () => {
  const s = setup(); s.ttsStart(0); s.flush(); s.spoken[0].onend();
  s.context.prefs.rate = 1.3; s.ttsStart(0, true); s.flush();
  assert.equal(s.spoken[2].text, '次の文。');
  assert.equal(s.spoken[2].rate, 1.3);
});
test('long Unicode text is bounded with no character loss', () => {
  const s = setup(); const text = '長い文章、'.repeat(90) + '😀'.repeat(250) + '終了。';
  const chunks = s.sentences(text);
  assert.equal(chunks.join(''), text);
  assert.ok(chunks.every(c => Array.from(c).length <= 120));
});
test('empty paragraphs do not recurse or hang', () => {
  const s = setup(Array(3000).fill(' ').concat(['最後。'])); s.ttsStart(0); s.flush();
  assert.equal(s.spoken[0].text, '最後。'); s.spoken[0].onend();
  assert.equal(s.tts.playing, false);
});
test('synchronous speech failure stops without skipping', () => {
  const s = setup(); s.synth.speak = () => { throw Error('engine failure'); };
  s.ttsStart(0); s.flush();
  assert.equal(s.tts.queue[0], '最初の文。');
  assert.equal(s.tts.playing, false); assert.equal(s.notices.length, 1);
});
test('leaving reader invalidates resume and delayed start', () => {
  const s = setup(); s.ttsStart(0); s.ttsStop(); s.flush();
  assert.equal(s.spoken.length, 0); assert.equal(s.tts.queue.length, 0);
});
