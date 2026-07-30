// "Data sources" modal: StatCan + OSM + basemap + all municipal statements
// from the CPND data_sources.csv (generated into attributions.json).
import ATTRIBUTIONS from './attributions.json';

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'text') node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const child of children) node.appendChild(child);
  return node;
}

function link(href, text) {
  return el('a', { href, target: '_blank', rel: 'noopener noreferrer', text });
}

export function initSourcesModal() {
  const modal = document.getElementById('sources-modal');
  const body = document.getElementById('sources-body');
  const openBtn = document.getElementById('sources-open');
  const closeBtn = document.getElementById('sources-close');

  for (const src of ATTRIBUTIONS.national) {
    const p = el('p', { class: 'national' });
    p.appendChild(el('strong', { text: `${src.name}. ` }));
    p.appendChild(document.createTextNode(`${src.statement} `));
    p.appendChild(link(src.licence_url, 'Licence'));
    body.appendChild(p);
  }

  for (const [prov, rows] of Object.entries(ATTRIBUTIONS.municipal)) {
    body.appendChild(el('h3', { text: prov }));
    for (const row of rows) {
      const p = el('p', { class: 'muni' });
      p.appendChild(el('strong', { text: `${row.municipality}: ` }));
      p.appendChild(document.createTextNode(`${row.statement} `));
      if (row.licence_url) p.appendChild(link(row.licence_url, 'Licence'));
      if (row.last_update) p.appendChild(document.createTextNode(` (updated ${row.last_update})`));
      body.appendChild(p);
    }
  }

  const open = () => {
    modal.hidden = false;
    closeBtn.focus();
  };
  const close = () => {
    modal.hidden = true;
    openBtn.focus();
  };
  openBtn.addEventListener('click', open);
  closeBtn.addEventListener('click', close);
  modal.addEventListener('click', (e) => {
    if (e.target === modal) close();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.hidden) close();
  });
}
