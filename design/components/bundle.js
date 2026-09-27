/* @ds-bundle: {"format":4,"namespace":"Filamentarium","components":[{"name":"Button"},{"name":"FilterPill"},{"name":"SearchField"},{"name":"NavItem"},{"name":"StatusChip"},{"name":"Sticker"},{"name":"DateStamp"},{"name":"Meter"},{"name":"Swatch"},{"name":"SpoolDrawing"},{"name":"SpoolSpine"},{"name":"Shelf"},{"name":"IndexCard"},{"name":"SlotCard"},{"name":"Bookplate"}]} */
(function () {
  var R = window.React;
  var h = R.createElement;

  function cx() {
    var out = [];
    for (var i = 0; i < arguments.length; i++) if (arguments[i]) out.push(arguments[i]);
    return out.join(' ');
  }
  function rest(props, keys) {
    var o = {};
    for (var k in props) if (Object.prototype.hasOwnProperty.call(props, k) && keys.indexOf(k) < 0) o[k] = props[k];
    return o;
  }
  function lum(hex) {
    var m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
    if (!m) return null;
    var n = parseInt(m[1], 16);
    function lin(c) { c = c / 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }
    return 0.2126 * lin((n >> 16) & 255) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
  }
  // Readable label colour on a filament colour: white or ink, whichever contrasts more.
  function inkOn(hex) {
    var L = lum(hex);
    if (L == null) return '#2e2419';
    var onWhite = 1.05 / (L + 0.05);
    var onInk = (L + 0.05) / (0.0191 + 0.05);
    return onWhite >= onInk ? '#ffffff' : '#2e2419';
  }
  function grams(g) {
    if (g == null) return '';
    return String(Math.round(g)).replace(/\B(?=(\d{3})+(?!\d))/g, ',') + ' g';
  }

  function Button(p) {
    var o = rest(p, ['variant', 'size', 'icon', 'className', 'children']);
    if (!o.type) o.type = 'button';
    o.className = cx('fm-btn', 'fm-btn--' + (p.variant || 'secondary'), p.size === 'lg' && 'fm-btn--lg', p.className);
    return h('button', o, p.icon || null, p.children);
  }

  function FilterPill(p) {
    var o = rest(p, ['pressed', 'className', 'children']);
    o.type = 'button';
    o['aria-pressed'] = p.pressed ? 'true' : 'false';
    o.className = cx('fm-pill', p.className);
    return h('button', o, p.children);
  }

  function searchIcon() {
    return h('svg', { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', 'aria-hidden': 'true' },
      h('circle', { cx: 11, cy: 11, r: 7 }),
      h('path', { d: 'M20 20l-3.5-3.5' }));
  }
  function SearchField(p) {
    var o = rest(p, ['label', 'className', 'style']);
    o.type = 'search';
    o['aria-label'] = p.label || 'Search the catalogue';
    o.className = 'fm-search-input';
    if (!o.placeholder) o.placeholder = 'Search by colour, brand, material or No.';
    return h('label', { className: cx('fm-search', p.className), style: p.style }, searchIcon(), h('input', o));
  }

  function NavItem(p) {
    return h('a', { href: p.href || '#', className: cx('fm-nav', p.current && 'is-current', p.className), 'aria-current': p.current ? 'page' : undefined },
      h('span', null, p.children),
      p.count != null ? h('span', { className: 'fm-nav-count' }, p.count) : null);
  }

  function StatusChip(p) {
    return h('span', { className: cx('fm-chip', 'fm-chip--' + (p.tone || 'neutral'), p.className) },
      p.dot ? h('span', { className: 'fm-chip-dot', 'aria-hidden': 'true' }) : null,
      p.children);
  }

  var STICKERS = { low: ['L', 'Low stock'], dry: ['D', 'Due for drying'] };
  function Sticker(p) {
    var kind = STICKERS[p.kind] ? p.kind : 'low';
    var s = STICKERS[kind];
    return h('span', { className: cx('fm-sticker', 'fm-sticker--' + kind, p.className), role: 'img', 'aria-label': s[1], title: s[1] }, s[0]);
  }

  function DateStamp(p) {
    var tilt = p.tilt == null ? -2 : p.tilt;
    return h('span', { className: cx('fm-stamp', p.className), style: { transform: 'rotate(' + tilt + 'deg)' } }, p.children);
  }

  function Meter(p) {
    var max = p.max || 1000;
    var v = Math.max(0, Math.min(max, p.value || 0));
    var pct = Math.round((v / max) * 100);
    return h('div', { className: cx('fm-meter', p.className) },
      h('div', { className: 'fm-meter-head' },
        h('span', { className: 'fm-meter-value' }, grams(v), h('span', { className: 'fm-meter-of' }, ' of ' + grams(max) + ' remaining')),
        h('span', { className: 'fm-meter-aside' }, (p.aside ? p.aside + ' · ' : '') + pct + '%')),
      h('div', { className: 'fm-meter-track', role: 'meter', 'aria-valuemin': 0, 'aria-valuemax': max, 'aria-valuenow': v, 'aria-label': p.label || 'Filament remaining' },
        h('div', { className: cx('fm-meter-fill', pct <= 15 && 'is-low'), style: { width: pct + '%' } })));
  }

  var SWATCH_SIZES = { sm: [32, 22], md: [64, 48], lg: [96, 72] };
  function Swatch(p) {
    var s = SWATCH_SIZES[p.size] || SWATCH_SIZES.md;
    return h('span', { className: cx('fm-swatch', p.className), style: { width: s[0], height: s[0] }, role: p.label ? 'img' : undefined, 'aria-label': p.label || undefined, 'aria-hidden': p.label ? undefined : 'true' },
      h('span', { className: 'fm-swatch-fill', style: { width: s[1], height: s[1], background: p.hex } }));
  }

  function SpoolDrawing(p) {
    var net = p.net || 1000;
    var rem = Math.max(0, Math.min(net, p.remaining == null ? net : p.remaining));
    var size = p.size || 300;
    var rIn = 52, rFull = 118;
    var r = Math.sqrt(rIn * rIn + (rem / net) * (rFull * rFull - rIn * rIn));
    var coil = inkOn(p.hex);
    var coils = [];
    for (var cr = r - 10; cr > rIn + 6; cr -= 10) {
      coils.push(h('circle', { key: 'c' + Math.round(cr), cx: 150, cy: 150, r: cr, fill: 'none', stroke: coil, strokeOpacity: 0.14, strokeWidth: 1 }));
    }
    return h('svg', { className: cx('fm-spool', p.className), width: size, height: size, viewBox: '0 0 300 300', role: 'img', 'aria-label': 'Spool drawing: ' + grams(rem) + ' of ' + grams(net) + ' remaining' },
      h('circle', { className: 'fm-spool-flange', cx: 150, cy: 150, r: 140 }),
      h('circle', { className: 'fm-spool-full', cx: 150, cy: 150, r: rFull }),
      rem > 0 ? h('circle', { cx: 150, cy: 150, r: r, fill: p.hex }) : null,
      coils,
      h('circle', { className: 'fm-spool-hub', cx: 150, cy: 150, r: rIn }),
      h('circle', { className: 'fm-spool-bore', cx: 150, cy: 150, r: 20 }));
  }

  function SpoolSpine(p) {
    var tag = p.href ? 'a' : 'div';
    var label = 'No. ' + p.no + ', ' + (p.material ? p.material + ' ' : '') + p.name +
      (p.grams != null ? ', ' + grams(p.grams) + ' remaining' : '') +
      (p.flag === 'low' ? ', low stock' : p.flag === 'dry' ? ', due for drying' : '');
    return h(tag, {
      href: p.href,
      className: cx('fm-spine', p.className),
      'aria-label': label,
      role: p.href ? undefined : 'img',
      style: { width: p.width || 44, height: p.height || 148, background: p.hex, color: p.fg || inkOn(p.hex) }
    },
      p.flag ? h(Sticker, { kind: p.flag }) : h('span', { className: 'fm-spine-no' }, p.no),
      h('span', { className: 'fm-spine-name' }, p.name),
      h('span', { className: 'fm-spine-g' }, p.grams != null ? Math.round(p.grams) + 'g' : ''));
  }

  function Shelf(p) {
    return h('section', { className: cx('fm-shelf', p.className) },
      h('div', { className: 'fm-shelf-head' },
        h('div', { className: 'fm-shelf-title' },
          h('h2', { className: 'fm-shelf-name' }, p.name),
          p.meta ? h('span', { className: cx('fm-shelf-meta', p.warn && 'is-warn') }, p.meta) : null),
        p.action || null),
      h('div', { className: 'fm-case' }, p.children));
  }

  function IndexCard(p) {
    var fields = p.fields || [];
    return h('article', { className: cx('fm-index', p.className) },
      h('header', { className: 'fm-index-head' },
        h('div', { className: 'fm-index-top' },
          h('span', { className: 'fm-index-accession' }, p.accession),
          p.status ? h(StatusChip, { tone: p.statusTone || 'shelf' }, p.status) : null),
        h('h1', { className: 'fm-index-title' }, p.title),
        p.subtitle ? h('p', { className: 'fm-index-sub' }, p.subtitle) : null),
      p.children ? h('div', { className: 'fm-index-body' }, p.children) : null,
      fields.length ? h('dl', { className: 'fm-index-fields' }, fields.map(function (f, i) {
        return h('div', { key: i, className: 'fm-index-field' }, h('dt', null, f[0]), h('dd', null, f[1]));
      })) : null);
  }

  function SlotCard(p) {
    var s = p.spool;
    if (!s) {
      return h('article', { className: cx('fm-slot', 'fm-slot--free', p.className) },
        h('span', { className: 'fm-slot-label' }, p.slot),
        h('div', { className: 'fm-slot-freebody' },
          h('div', { className: 'fm-slot-name' }, 'Slot free'),
          h('p', { className: 'fm-slot-hint' }, 'Scan a spool’s bookplate, or pick one from the shelves.')),
        h(Button, { variant: 'primary', onClick: p.onLend }, 'Lend a spool'));
    }
    return h('article', { className: cx('fm-slot', p.inUse && 'is-in-use', p.className) },
      h('div', { className: 'fm-slot-top' },
        h('span', { className: 'fm-slot-label' }, p.slot),
        p.inUse ? h('span', { className: 'fm-slot-inuse' }, 'In use') : null),
      h(Swatch, { hex: s.hex, size: 'md' }),
      h('div', null,
        h('div', { className: 'fm-slot-name' }, s.name),
        h('div', { className: 'fm-slot-meta' }, s.material + ' · No. ' + s.no)),
      h('dl', { className: 'fm-slot-facts' },
        h('div', null, h('dt', null, 'Out since'), h('dd', null, s.since)),
        h('div', null, h('dt', null, 'Used this loan'), h('dd', null, grams(s.used))),
        h('div', null, h('dt', null, 'On the spool'), h('dd', null, grams(s.left)))),
      h('div', { className: 'fm-slot-spacer' }),
      h(Button, { onClick: p.onReturn, 'aria-label': 'Return ' + s.name + ', No. ' + s.no + ', to the shelf' }, 'Return to shelf'));
  }

  function Bookplate(p) {
    var specs = p.specs || [];
    return h('div', { className: cx('fm-plate', p.className) },
      h('div', { className: 'fm-plate-inner' },
        h('div', { className: 'fm-plate-main' },
          h('div', null,
            h('div', { className: 'fm-plate-exlibris' }, 'Ex libris · Filamentarium'),
            h('div', { className: 'fm-plate-no' }, 'No. ' + p.no)),
          h('div', null,
            h('div', { className: 'fm-plate-name' }, p.name),
            p.subtitle ? h('div', { className: 'fm-plate-sub' }, p.subtitle) : null),
          h('div', { className: 'fm-plate-specs' }, specs.map(function (s, i) { return h('span', { key: i }, s); }))),
        h('div', { className: 'fm-plate-side' },
          h('div', { className: 'fm-plate-qr' }, p.qr || h(R.Fragment, null, h('span', null, '[QR CODE]'), h('span', null, 'opens No. ' + p.no))),
          p.acquired ? h('div', { className: 'fm-plate-acq' }, 'Acquired ' + p.acquired) : null)));
  }

  var api = {
    Button: Button, FilterPill: FilterPill, SearchField: SearchField, NavItem: NavItem,
    StatusChip: StatusChip, Sticker: Sticker, DateStamp: DateStamp, Meter: Meter,
    Swatch: Swatch, SpoolDrawing: SpoolDrawing, SpoolSpine: SpoolSpine, Shelf: Shelf,
    IndexCard: IndexCard, SlotCard: SlotCard, Bookplate: Bookplate,
    inkOn: inkOn
  };
  window.Filamentarium = Object.assign(window.Filamentarium || {}, api);
})();
