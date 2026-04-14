// storage.js — All data lives in localStorage under one key.
// Each entry is a versioned snapshot of the framework summary.

const STORAGE_KEY = 'mirrormind_versions';

const Storage = {

  getAll() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    } catch {
      return [];
    }
  },

  getById(id) {
    return this.getAll().find(v => v.id === id) || null;
  },

  getPrevious(versionNumber) {
    return this.getAll().find(v => v.versionNumber === versionNumber - 1) || null;
  },

  add(content) {
    const all     = this.getAll();
    const nextNum = all.length > 0 ? Math.max(...all.map(v => v.versionNumber)) + 1 : 1;
    const entry   = {
      id:            crypto.randomUUID(),
      versionNumber: nextNum,
      content:       content.trim(),
      timestamp:     new Date().toISOString(),
      autoTitle:     extractTitle(content),
    };
    // Store newest-first
    all.unshift(entry);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
    return entry;
  },

};

function extractTitle(content) {
  return content.split('\n').map(l => l.replace(/^#+\s*/, '').trim()).find(l => l.length > 0)
    || 'Untitled';
}
