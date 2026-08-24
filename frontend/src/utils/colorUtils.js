export function groupSpoolsByMaterialColor(spools, materials, colors, manufacturers, spoolTypes, hideEmpty, refills = []) {
  const colorMap = Object.fromEntries(colors.map(c => [c.id, c.name]));
  const manufacturerMap = Object.fromEntries(manufacturers.map(m => [m.id, m.name]));
  const spoolTypeMap = Object.fromEntries(spoolTypes.map(s => [s.id, s.name]));
  const grouped = {};
  materials.forEach(material => {
    grouped[material.name] = {};
    const spoolColors = spools.filter(s => s.material_id === material.id).map(s => s.color_id);
    const refillColors = (refills || []).filter(r => r.material_id === material.id).map(r => r.color_id);
    const colorIdsForMaterial = Array.from(new Set([...spoolColors, ...refillColors]));
    // Sort colorIds by rainbow order (within: low-stock first prioritization)
    colorIdsForMaterial.sort((a, b) => {
      const nameA = colorMap[a] || '';
      const nameB = colorMap[b] || '';
      const keyA = colorSortKey(nameA);
      const keyB = colorSortKey(nameB);
      if (keyA !== keyB) return keyA - keyB;
      const spoolsA = spools.filter(s => s.material_id === material.id && s.color_id === a);
      const spoolsB = spools.filter(s => s.material_id === material.id && s.color_id === b);
      const isLowA = spoolsA.some(s => !s.is_empty && s.weight_remaining <= (s.low_stock_threshold ?? 100));
      const isLowB = spoolsB.some(s => !s.is_empty && s.weight_remaining <= (s.low_stock_threshold ?? 100));
      return (isLowB - isLowA);
    });
    colorIdsForMaterial.forEach(colorId => {
      const color = colorMap[colorId] || 'Unknown';
      const spoolsForCombo = spools.filter(s => s.material_id === material.id && s.color_id === colorId);
      const nonEmpty = spoolsForCombo.filter(s => !s.is_empty);
      if (hideEmpty && nonEmpty.length === 0) return;
      grouped[material.name][color] = spoolsForCombo.map(spool => ({
        ...spool,
        manufacturer: manufacturerMap[spool.manufacturer_id] || 'Unknown',
        spool_type: spoolTypeMap[spool.spool_type_id] || 'Unknown',
        colorName: color,
        materialName: material.name
      }));
    });
  });
  // Reorder each material group's colors by rainbow order (stable within)
  for (const mat of Object.keys(grouped)) {
    const entries = Object.entries(grouped[mat]);
    entries.sort((a, b) => colorSortKey(a[0]) - colorSortKey(b[0]));
    grouped[mat] = Object.fromEntries(entries);
  }
  return grouped;
}

// Calculate relative luminance of a hex color (0-1, higher = lighter)
export function getLuminance(hex) {
  if (!hex || !hex.startsWith('#')) return 0.5;
  const rgb = hex.length === 4
    ? [parseInt(hex[1] + hex[1], 16), parseInt(hex[2] + hex[2], 16), parseInt(hex[3] + hex[3], 16)]
    : [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)];
  const [r, g, b] = rgb.map(c => {
    c = c / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

// Returns true if the color is light (needs dark text)
export function isLightColor(hex) {
  return getLuminance(hex) > 0.5;
}

export function parseColorName(colorName) {
  // Known color map
  const colorMap = {
    red: '#e74c3c',
    grey: '#888',
    gray: '#888',
    white: '#fff',
    black: '#222',
    clear: '#bfefff',
    blue: '#3498db',
    green: '#27ae60',
    yellow: '#f1c40f',
    orange: '#e67e22',
    purple: '#9b59b6',
    pink: '#ff69b4',
    brown: '#8B4513',
    gold: '#FFD700',
    silver: '#C0C0C0',
    bronze: '#CD7F32',
    copper: '#B87333',
    teal: '#1abc9c',
    cyan: '#00bcd4',
    magenta: '#e91e63',
    lime: '#8bc34a',
    beige: '#f5f5dc',
    ivory: '#fffff0',
    cream: '#fffdd0',
    natural: '#d4c4a8',
    navy: '#001f3f',
    maroon: '#800000',
    olive: '#808000',
    aqua: '#00ffff',
    turquoise: '#40e0d0',
    coral: '#ff7f50',
    salmon: '#fa8072',
    peach: '#ffcba4',
    lavender: '#e6e6fa',
    violet: '#ee82ee',
    indigo: '#4b0082',
    rainbow: 'rainbow',
    default: '#bbb'
  };
  if (!colorName) return [colorMap.default];
  const lower = colorName.toLowerCase();
  if (lower.includes('rainbow')) return ['rainbow'];
  // Split on common delimiters
  const parts = lower.split(/\s*(?:,|\/|\+|and|&|-)\s*/);
  const found = parts.map(p => colorMap[p.trim()] || null).filter(Boolean);
  if (found.length > 1) return found;
  if (found.length === 1) return found;
  // Try to match any single color word in the string
  for (const key of Object.keys(colorMap)) {
    if (lower.includes(key)) return [colorMap[key]];
  }
  return [colorMap.default];
}

// Rainbow order for color names; fallback to hex -> hue
const rainbowOrder = ['red','coral','salmon','peach','orange','gold','yellow','lime','green','teal','cyan','aqua','turquoise','blue','navy','indigo','purple','violet','magenta','pink','lavender','brown','maroon','olive','copper','bronze','beige','cream','ivory','natural','black','grey','gray','silver','white','clear'];
export function colorSortKey(colorName) {
  const lower = (colorName || '').toLowerCase();
  const idx = rainbowOrder.indexOf(lower);
  if (idx >= 0) return idx;
  try {
    // crude hex hue sort: map parsed color to H via canvas; fallback to end
    const map = parseColorName(colorName);
    const hex = map[0];
    if (!hex || !hex.startsWith('#')) return 9999;
    // approximate hue buckets by first component order
    return parseInt(hex.slice(1,3), 16); // not perfect, stable enough
  } catch {
    return 9999;
  }
}

export function formatGrams(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return value;
  return Math.round(value);
}
