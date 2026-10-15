/* Gaya visual untuk tahap 3 Breakdown: prompt (English) + thumbnail ilustrasi SVG.
   Semua thumbnail menggambar adegan yang sama (karakter, pohon, bukit, matahari) supaya gaya mudah dibandingkan.
   Pratinjau asli (Z-Image) dibuat di ui.html dan menggantikan thumbnail ini. */
const STYLES = [
  {id: "clay3d", photo: {id: 7083142, by: "Nothing Ahead", page: "https://www.pexels.com/photo/cute-figurines-on-table-in-room-7083142/"}, name: "3D Clay / Plush", desc: "Lucu, lembut, cocok untuk anak-anak.",
   prompt: "cute 3D animation, soft clay and plush textures, rounded chunky shapes, pastel colors, soft studio lighting, tilt-shift depth of field",
   lighting: "soft warm studio light, gentle bounce light", palette: "pastel peach, mint green, sky blue"},
  {id: "anime", name: "Anime", desc: "Warna cerah, garis tegas, mata ekspresif.",
   prompt: "anime style, clean cel shading, bold line art, vibrant saturated colors, expressive big eyes, painted sky with fluffy clouds",
   lighting: "bright daylight with crisp cel shadows", palette: "sky blue, fresh green, vivid pink"},
  {id: "cinema", photo: {id: 4618595, by: "", page: "https://www.pexels.com/photo/a-silhouette-of-a-man-on-a-mountain-peak-during-the-golden-hour-4618595/"}, name: "Sinematik", desc: "Seperti film live action.",
   prompt: "cinematic live-action film still, photorealistic, anamorphic lens, shallow depth of field, subtle film grain, teal and orange color grade",
   lighting: "golden hour backlight, soft rim light", palette: "teal shadows, warm orange highlights"},
  {id: "water", photo: {id: 6925155, by: "", page: "https://www.pexels.com/photo/watercolor-painting-of-flowers-on-white-paper-6925155/"}, name: "Cat air", desc: "Lembut, ringan, seperti lukisan cat air.",
   prompt: "soft watercolor illustration, visible paper texture, gentle color bleeds, loose brush strokes, light airy palette",
   lighting: "soft diffused daylight", palette: "light blue, sage green, warm peach"},
  {id: "storybook", name: "Buku cerita", desc: "Ilustrasi buku anak, hangat dan nyaman.",
   prompt: "children's storybook illustration, gouache painting, warm textured brushwork, whimsical cozy atmosphere",
   lighting: "warm afternoon light", palette: "honey yellow, olive green, brick red"},
  {id: "pixel", name: "Pixel art", desc: "Gaya game retro 16-bit.",
   prompt: "16-bit pixel art, retro video game style, limited color palette, crisp pixels, no anti-aliasing",
   lighting: "flat bright game lighting", palette: "retro NES blue, green, red"},
  {id: "paper", photo: {id: 5554001, by: "", page: "https://www.pexels.com/photo/people-artistic-paper-cutout-5554001/"}, name: "Paper cut-out", desc: "Kerajinan kertas berlapis, terasa buatan tangan.",
   prompt: "layered paper cut-out craft style, handmade cardstock textures, soft drop shadows between paper layers, stop-motion feel",
   lighting: "soft top light casting small shadows between layers", palette: "teal, mustard, coral, kraft brown"},
  {id: "flat", name: "Flat vector", desc: "Bersih, sederhana, seperti motion graphics.",
   prompt: "flat vector illustration, simple geometric shapes, bold limited color palette, clean minimal motion-graphics look",
   lighting: "flat even lighting, no shadows", palette: "navy, coral, mustard, teal"},
  {id: "lowpoly", photo: {id: 1097809, by: "Abdullah Esmail", page: "https://www.pexels.com/photo/low-poly-polygon-polygonal-1097809/"}, name: "Low poly 3D", desc: "3D bersudut, geometris.",
   prompt: "low poly 3D style, faceted geometric surfaces, simple flat-shaded polygons, stylized lighting",
   lighting: "directional sun light with faceted shading", palette: "fresh greens, sand, sky blue"},
  {id: "comic", photo: {id: 589871, by: "Srini Reddy", page: "https://www.pexels.com/photo/color-pencil-drawing-manga-art-painting-589871/"}, name: "Komik / manga", desc: "Hitam putih, tinta, raster.",
   prompt: "black and white manga comic style, inked line art, screentone halftone shading, dynamic speed lines",
   lighting: "high contrast ink shadows", palette: "black and white with gray screentone"},
  {id: "vintage", photo: {id: 30005330, by: "M7MD", page: "https://www.pexels.com/photo/vintage-film-projector-on-stand-against-textured-wall-30005330/", css: "sepia(.85) contrast(1.05)"}, name: "Kartun klasik", desc: "Kartun tahun 1930-an, sepia.",
   prompt: "1930s vintage rubber-hose cartoon, black and white with sepia tint, film grain and scratches, bouncy exaggerated animation",
   lighting: "flat vintage lighting with vignette", palette: "sepia, black, cream"},
  {id: "crayon", photo: {id: 8524997, by: "", page: "https://www.pexels.com/photo/close-up-of-a-child-s-drawing-of-a-family-on-paper-8524997/"}, name: "Gambar krayon", desc: "Seperti gambar tangan anak.",
   prompt: "child's crayon drawing style, wobbly hand-drawn lines, waxy crayon texture on white paper, bright playful colors",
   lighting: "flat, no realistic lighting", palette: "bright red, yellow, green, blue"},
  {id: "neon", photo: {id: 18867525, by: "Johannes Plenio", page: "https://www.pexels.com/photo/night-city-street-after-rain-illuminated-by-colorful-neon-signs-reflecting-on-a-wet-road-18867525/"}, name: "Neon cyberpunk", desc: "Malam, lampu neon, futuristik.",
   prompt: "neon cyberpunk style, dark night scene, glowing magenta and cyan neon lights, wet reflections, futuristic city atmosphere",
   lighting: "glowing neon rim lights, dark ambient", palette: "magenta, cyan, deep purple"},
];

/* Foto contoh dari Pexels (lisensi Pexels: gratis dipakai, atribusi tidak wajib; tetap kami cantumkan).
   Diunduh oleh app di PC pengguna lewat /api/stylethumb dan disimpan di cache/styles/; gagal = tetap ilustrasi SVG. */
const pexelsURL = (id) => `https://images.pexels.com/photos/${id}/pexels-photo-${id}.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=640&w=360`;

/* ---- potongan adegan bersama (viewBox 90x160, vertikal 9:16) */
const SVGBITS = {
  hill: "M0 104 Q22 86 48 99 T90 92 V160 H0Z",
  ground: "M0 121 Q45 109 90 123 V160 H0Z",
  smile: "M46.5 109.5 Q50 112.5 53.5 109.5",
};
function svgChar(o) {
  const L = o.line ? ` stroke="${o.line}" stroke-width="${o.lw || 1}"` : "";
  const er = o.big ? 3.1 : 2.1;
  const hl = o.big ? `<circle cx="46.2" cy="101.8" r="1.1" fill="#fff"/><circle cx="56.2" cy="101.8" r="1.1" fill="#fff"/>`
    : `<circle cx="45.7" cy="102.3" r=".7" fill="#fff"/><circle cx="55.7" cy="102.3" r=".7" fill="#fff"/>`;
  return `<g${o.f ? ` filter="url(#${o.f})"` : ""}><ellipse cx="50" cy="129" rx="14" ry="16" fill="${o.body}"${L}/>
<circle cx="50" cy="104" r="13" fill="${o.head}"${L}/>${o.hair || ""}
<circle cx="45" cy="103" r="${er}" fill="${o.eye}"/><circle cx="55" cy="103" r="${er}" fill="${o.eye}"/>${o.noHl ? "" : hl}
${o.cheek ? `<ellipse cx="41.5" cy="108.5" rx="2.4" ry="1.4" fill="${o.cheek}" opacity=".8"/><ellipse cx="58.5" cy="108.5" rx="2.4" ry="1.4" fill="${o.cheek}" opacity=".8"/>` : ""}
<path d="${SVGBITS.smile}" fill="none" stroke="${o.mouth || o.eye}" stroke-width=".9" stroke-linecap="round"/></g>`;
}
const svgTree = (o) => `<g${o.f ? ` filter="url(#${o.f})"` : ""}><rect x="10" y="88" width="5" height="27" rx="1" fill="${o.trunk}"${o.L || ""}/><circle cx="12.5" cy="80" r="12.5" fill="${o.leaf}"${o.L || ""}/></g>`;
const lin = (id, a, b, y2) => `<linearGradient id="${id}" x1="0" y1="0" x2="0" y2="${y2 || 1}"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient>`;
const rad = (id, a, b) => `<radialGradient id="${id}" cx=".35" cy=".3" r=".85"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></radialGradient>`;
const grainF = (id, f) => `<filter id="${id}" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="${f || .9}" numOctaves="2" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter>`;
const grain = (id, op) => `<rect width="90" height="160" filter="url(#${id})" opacity="${op}"/>`;
const vignette = (id) => `<radialGradient id="${id}" cx=".5" cy=".5" r=".75"><stop offset=".55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".75"/></radialGradient>`;

const SVGSTYLE = {
  clay3d: (k) => [`${lin(k + "s", "#ffd6c0", "#fff1e3")}${rad(k + "h", "#ffd2a8", "#e99560")}${rad(k + "b", "#a8def0", "#4fa3c4")}
${rad(k + "hi", "#d4f3dc", "#7cc49a")}${rad(k + "g", "#fff0c9", "#e8bd7c")}${rad(k + "l", "#b6ecc4", "#47a06d")}${rad(k + "sun", "#fffbe0", "#ffd36b")}
<filter id="${k}d" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="2" stdDeviation="1.6" flood-opacity=".28"/></filter>`,
    `<rect width="90" height="160" fill="url(#${k}s)"/><circle cx="68" cy="32" r="11" fill="url(#${k}sun)" filter="url(#${k}d)"/>
<path d="${SVGBITS.hill}" fill="url(#${k}hi)"/><path d="${SVGBITS.ground}" fill="url(#${k}g)"/>
${svgTree({trunk: "#c4865a", leaf: `url(#${k}l)`, f: k + "d"})}<ellipse cx="50" cy="146" rx="14" ry="2.6" fill="#000" opacity=".14"/>
${svgChar({body: `url(#${k}b)`, head: `url(#${k}h)`, eye: "#3a2a2a", cheek: "#ff8a8a", f: k + "d"})}`],
  anime: (k) => [lin(k + "s", "#3f97ff", "#c8ecff"),
    `<rect width="90" height="160" fill="url(#${k}s)"/><g fill="#fff"><ellipse cx="22" cy="30" rx="15" ry="6"/><ellipse cx="32" cy="26" rx="10" ry="7"/><ellipse cx="70" cy="52" rx="13" ry="5"/></g>
<path d="${SVGBITS.hill}" fill="#5dbb63" stroke="#20303a" stroke-width=".9"/><path d="${SVGBITS.ground}" fill="#9ee36b" stroke="#20303a" stroke-width=".9"/>
${svgTree({trunk: "#8a5a3b", leaf: "#3fa34d", L: ` stroke="#20303a" stroke-width=".9"`})}
${svgChar({body: "#ff6f91", head: "#ffe2cc", eye: "#3b2a66", big: 1, cheek: "#ff9db0", line: "#20303a", lw: .9,
  hair: `<path d="M36.5 103 Q36 87 50 88.5 Q64 87 63.5 103 Q60 94 54 95 L50 92 L46 95 Q40 94 36.5 103Z" fill="#3b2a66" stroke="#20303a" stroke-width=".9"/>`})}`],
  cinema: (k) => [`${lin(k + "s", "#0c2430", "#d9813f", .72)}${vignette(k + "v")}${grainF(k + "g")}<filter id="${k}b"><feGaussianBlur stdDeviation="4"/></filter>`,
    `<rect width="90" height="160" fill="url(#${k}s)"/><circle cx="64" cy="100" r="16" fill="#ffc17a" filter="url(#${k}b)"/><circle cx="64" cy="100" r="6" fill="#ffe2b0"/>
<path d="${SVGBITS.hill}" fill="#241a14"/><path d="${SVGBITS.ground}" fill="#120d0a"/>${svgTree({trunk: "#0b0807", leaf: "#0b0807"})}
${svgChar({body: "#0a0808", head: "#0a0808", eye: "#0a0808", noHl: 1, mouth: "#0a0808"})}<path d="M62 100 A13 13 0 0 1 61 112" stroke="#ffb46b" stroke-width=".7" fill="none" transform="translate(-0 -4)"/>
<rect width="90" height="160" fill="url(#${k}v)"/>${grain(k + "g", .16)}<rect width="90" height="13" fill="#000"/><rect y="147" width="90" height="13" fill="#000"/>`],
  water: (k) => [`<filter id="${k}w" x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="fractalNoise" baseFrequency=".035" numOctaves="3" seed="4" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="5"/></filter>${grainF(k + "g", .7)}`,
    `<rect width="90" height="160" fill="#f8f3e8"/><g filter="url(#${k}w)" opacity=".78"><rect x="2" y="2" width="86" height="104" fill="#a3cdea"/>
<circle cx="66" cy="32" r="11" fill="#ffd08f"/><path d="${SVGBITS.hill}" fill="#a9d6a1"/><path d="${SVGBITS.ground}" fill="#ecd0a2"/>
${svgTree({trunk: "#b08a6a", leaf: "#78b583"})}${svgChar({body: "#ec9fae", head: "#f6c9a6", eye: "#4c4b5e", cheek: "#ff9a9a", noHl: 1})}</g>${grain(k + "g", .09)}`],
  storybook: (k) => [`${lin(k + "s", "#fde6b4", "#f4bf86")}<filter id="${k}w"><feTurbulence type="fractalNoise" baseFrequency=".06" numOctaves="2" seed="2" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="1.8"/></filter>${grainF(k + "g", .55)}`,
    `<rect width="90" height="160" fill="url(#${k}s)"/><g filter="url(#${k}w)"><circle cx="66" cy="34" r="10" fill="#fff4cf"/>
<g fill="none" stroke="#6b4a35" stroke-width=".6"><path d="M20 40 q3 -3 6 0 q3 -3 6 0"/><path d="M36 52 q2 -2 4 0 q2 -2 4 0"/></g>
<path d="${SVGBITS.hill}" fill="#a3c06e" stroke="#6b4a35" stroke-width=".7"/><path d="${SVGBITS.ground}" fill="#dca66a" stroke="#6b4a35" stroke-width=".7"/>
${svgTree({trunk: "#7a5236", leaf: "#5f9a57", L: ` stroke="#6b4a35" stroke-width=".7"`})}${svgChar({body: "#c9573f", head: "#f2bc93", eye: "#4a3226", cheek: "#ee8a6a", line: "#6b4a35", lw: .7})}</g>${grain(k + "g", .14)}`],
  pixel: (k) => [`<filter id="${k}p" x="0" y="0" width="100%" height="100%"><feFlood x="2" y="2" height="1" width="1"/><feComposite width="4" height="4"/><feTile result="a"/><feComposite in="SourceGraphic" in2="a" operator="in"/><feMorphology operator="dilate" radius="2"/></filter>`,
    `<g filter="url(#${k}p)"><rect width="90" height="160" fill="#5c94fc"/><rect x="58" y="22" width="20" height="20" fill="#fcd800"/>
<path d="${SVGBITS.hill}" fill="#00a800"/><path d="${SVGBITS.ground}" fill="#c84c0c"/><rect y="138" width="90" height="22" fill="#a83c08"/>
${svgTree({trunk: "#7c3c00", leaf: "#00d800"})}
<rect x="40" y="88" width="20" height="8" fill="#7c3c00"/><rect x="38" y="96" width="24" height="20" fill="#fcbcb0"/><rect x="38" y="92" width="4" height="12" fill="#7c3c00"/><rect x="58" y="92" width="4" height="12" fill="#7c3c00"/>
<rect x="42" y="100" width="4" height="4" fill="#000"/><rect x="54" y="100" width="4" height="4" fill="#000"/><rect x="46" y="108" width="8" height="4" fill="#a80020"/>
<rect x="36" y="116" width="28" height="24" fill="#e40058"/><rect x="32" y="120" width="4" height="12" fill="#fcbcb0"/><rect x="64" y="120" width="4" height="12" fill="#fcbcb0"/>
<rect x="40" y="140" width="8" height="6" fill="#0058f8"/><rect x="52" y="140" width="8" height="6" fill="#0058f8"/></g>`],
  paper: (k) => [`<filter id="${k}d" x="-20%" y="-20%" width="140%" height="140%"><feTurbulence type="fractalNoise" baseFrequency=".08" numOctaves="2" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="1.2" result="r"/><feDropShadow in="r" dx=".6" dy="1.3" stdDeviation=".7" flood-opacity=".45"/></filter>${grainF(k + "g", .6)}`,
    `<rect width="90" height="160" fill="#e8d8bc"/><rect x="3" y="3" width="84" height="104" rx="2" fill="#8cc5c9" filter="url(#${k}d)"/>
<circle cx="66" cy="32" r="10" fill="#f3b94a" filter="url(#${k}d)"/><path d="${SVGBITS.hill}" fill="#5e9d8e" filter="url(#${k}d)"/><path d="${SVGBITS.ground}" fill="#d99a59" filter="url(#${k}d)"/>
${svgTree({trunk: "#8a5b3a", leaf: "#3e7c5d", f: k + "d"})}${svgChar({body: "#e2634b", head: "#f5d4ab", eye: "#2f2a28", cheek: "#ef8f7d", f: k + "d", noHl: 1})}${grain(k + "g", .12)}`],
  flat: (k) => ["",
    `<rect width="90" height="160" fill="#1f2a5a"/><g fill="#fff" opacity=".55"><circle cx="15" cy="20" r=".9"/><circle cx="34" cy="38" r=".7"/><circle cx="80" cy="15" r=".8"/><circle cx="52" cy="22" r=".6"/></g>
<circle cx="66" cy="40" r="12" fill="#ff7a59"/><path d="${SVGBITS.hill}" fill="#2f3f7a"/><path d="${SVGBITS.ground}" fill="#f2c14e"/>
<rect x="10" y="88" width="5" height="27" fill="#1f2a5a"/><path d="M0 92 L12.5 62 L25 92Z" fill="#2bb39b"/>
<rect x="36" y="114" width="28" height="31" rx="6" fill="#ff7a59"/><circle cx="50" cy="104" r="13" fill="#ffd6b0"/><circle cx="45" cy="103" r="2" fill="#1f2a5a"/><circle cx="55" cy="103" r="2" fill="#1f2a5a"/>
<path d="${SVGBITS.smile}" fill="none" stroke="#1f2a5a" stroke-width="1" stroke-linecap="round"/>`],
  lowpoly: (k) => [lin(k + "s", "#7cc6f7", "#dff3ff"),
    `<rect width="90" height="160" fill="url(#${k}s)"/><polygon points="58,22 70,26 74,38 64,44 54,38 52,28" fill="#ffd45e"/><polygon points="58,22 70,26 64,44 52,28" fill="#ffe28a"/>
<polygon points="0,104 18,84 34,100" fill="#6fb87f"/><polygon points="18,84 34,100 46,92" fill="#4b8f60"/><polygon points="34,100 60,86 90,96 90,110 0,110 0,104" fill="#5aa36f"/>
<polygon points="0,110 90,110 90,160 0,160" fill="#d9ba72"/><polygon points="0,122 45,112 90,124 90,160 0,160" fill="#c9a862"/><polygon points="0,140 50,128 90,145 90,160 0,160" fill="#b8975a"/>
<rect x="10" y="88" width="5" height="27" fill="#7d5737"/><polygon points="12.5,60 26,92 12.5,92" fill="#3f8f5a"/><polygon points="12.5,60 -1,92 12.5,92" fill="#57a870"/>
<polygon points="36,128 50,113 64,128 58,145 42,145" fill="#4a77d1"/><polygon points="50,113 64,128 58,145 50,140" fill="#3a63b5"/>
<polygon points="50,91 61,97.5 61,110.5 50,117 39,110.5 39,97.5" fill="#f5b183"/><polygon points="50,91 61,97.5 61,110.5 50,117" fill="#e39a6d"/>
<rect x="43.5" y="101.5" width="3" height="3" fill="#2a2a2a"/><rect x="53.5" y="101.5" width="3" height="3" fill="#2a2a2a"/><polygon points="46.5,109.5 53.5,109.5 50,112" fill="#2a2a2a"/>`],
  comic: (k) => [`<pattern id="${k}h" width="3" height="3" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r=".75" fill="#000"/></pattern>`,
    `<rect width="90" height="160" fill="#fff"/><rect width="90" height="100" fill="url(#${k}h)" opacity=".35"/>
<g stroke="#000" stroke-width=".45" opacity=".55">${Array.from({length: 18}, (_, i) => { const a = i / 18 * Math.PI * 2; return `<line x1="${50 + Math.cos(a) * 24}" y1="${110 + Math.sin(a) * 24}" x2="${50 + Math.cos(a) * 95}" y2="${110 + Math.sin(a) * 95}"/>`; }).join("")}</g>
<path d="${SVGBITS.hill}" fill="url(#${k}h)" stroke="#000" stroke-width="1.4"/><path d="${SVGBITS.ground}" fill="#fff" stroke="#000" stroke-width="1.4"/>
${svgTree({trunk: "#fff", leaf: "#fff", L: ` stroke="#000" stroke-width="1.4"`})}
${svgChar({body: `url(#${k}h)`, head: "#fff", eye: "#000", big: 1, line: "#000", lw: 1.5,
  hair: `<path d="M36.5 103 Q36 87 50 88.5 Q64 87 63.5 103 Q60 94 54 95 L50 92 L46 95 Q40 94 36.5 103Z" fill="#000"/>`})}
<rect x="1.5" y="1.5" width="87" height="157" fill="none" stroke="#000" stroke-width="2.5"/>`],
  vintage: (k) => [`<filter id="${k}sp"><feColorMatrix values=".393 .769 .189 0 0 .349 .686 .168 0 0 .272 .534 .131 0 0 0 0 0 1 0"/></filter>${vignette(k + "v")}${grainF(k + "g")}`,
    `<g filter="url(#${k}sp)"><rect width="90" height="160" fill="#e6e1d6"/><circle cx="66" cy="32" r="10" fill="#fff" stroke="#111" stroke-width="1.2"/>
<path d="${SVGBITS.hill}" fill="#a8a294" stroke="#111" stroke-width="1.2"/><path d="${SVGBITS.ground}" fill="#cbc5b6" stroke="#111" stroke-width="1.2"/>
${svgTree({trunk: "#3a3632", leaf: "#6e685c", L: ` stroke="#111" stroke-width="1.2"`})}
<path d="M38 125 Q28 118 30 108" fill="none" stroke="#111" stroke-width="2" stroke-linecap="round"/><path d="M62 125 Q72 132 70 142" fill="none" stroke="#111" stroke-width="2" stroke-linecap="round"/>
<ellipse cx="50" cy="129" rx="13" ry="15" fill="#111"/><circle cx="29.5" cy="107" r="3" fill="#fbf7ee" stroke="#111" stroke-width="1"/><circle cx="70.5" cy="143" r="3" fill="#fbf7ee" stroke="#111" stroke-width="1"/>
<circle cx="50" cy="104" r="12.5" fill="#fbf7ee" stroke="#111" stroke-width="1.4"/><ellipse cx="50" cy="93" rx="12" ry="2.2" fill="#111"/><path d="M42 93 Q42 82 50 82 Q58 82 58 93Z" fill="#111"/><ellipse cx="45.5" cy="102" rx="1.7" ry="3.2" fill="#111"/><ellipse cx="54.5" cy="102" rx="1.7" ry="3.2" fill="#111"/>
<ellipse cx="50" cy="107.5" rx="2.4" ry="1.6" fill="#111"/><path d="M44 110 Q50 115 56 110" fill="none" stroke="#111" stroke-width="1.1" stroke-linecap="round"/></g>
<g stroke="#fff" stroke-width=".35" opacity=".5"><line x1="20" y1="0" x2="21" y2="160"/><line x1="71" y1="0" x2="70" y2="160"/></g>
<rect width="90" height="160" fill="url(#${k}v)"/>${grain(k + "g", .2)}`],
  crayon: (k) => {
    const hatch = (id, c) => `<pattern id="${k}${id}" width="2.4" height="2.4" patternUnits="userSpaceOnUse" patternTransform="rotate(35)"><line x1="0" y1="0" x2="0" y2="2.4" stroke="${c}" stroke-width="1.3"/></pattern>`;
    return [`<filter id="${k}r" x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="1.9"/></filter>
${hatch("y", "#ffd400")}${hatch("g", "#38c172")}${hatch("b", "#c98a4b")}${hatch("p", "#ffb38a")}${hatch("rd", "#ef3e4a")}${hatch("s", "#6cb8ff")}${hatch("t", "#2f9e57")}`,
      `<rect width="90" height="160" fill="#fffdf6"/><g filter="url(#${k}r)" stroke-linecap="round" stroke-linejoin="round"><rect x="0" y="0" width="90" height="60" fill="url(#${k}s)" opacity=".6"/>
<circle cx="66" cy="32" r="9" fill="url(#${k}y)" stroke="#f2b400" stroke-width="1.4"/>
<g stroke="#f2b400" stroke-width="1.3">${Array.from({length: 8}, (_, i) => { const a = i / 8 * Math.PI * 2; return `<line x1="${66 + Math.cos(a) * 12}" y1="${32 + Math.sin(a) * 12}" x2="${66 + Math.cos(a) * 17}" y2="${32 + Math.sin(a) * 17}"/>`; }).join("")}</g>
<path d="${SVGBITS.hill}" fill="url(#${k}g)" stroke="#23a35a" stroke-width="1.4"/><path d="${SVGBITS.ground}" fill="url(#${k}b)" stroke="#9c6430" stroke-width="1.4"/>
${svgTree({trunk: `url(#${k}b)`, leaf: `url(#${k}t)`, L: ` stroke="#23793f" stroke-width="1.4"`})}
${svgChar({body: `url(#${k}rd)`, head: `url(#${k}p)`, eye: "#222", line: "#e0602a", lw: 1.4, noHl: 1})}</g>`];
  },
  neon: (k) => [`${lin(k + "sun", "#ffd23f", "#ff2bd6")}<filter id="${k}gl" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="1.3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>`,
    `<rect width="90" height="160" fill="#0b0820"/><circle cx="45" cy="70" r="20" fill="url(#${k}sun)" filter="url(#${k}gl)"/>
<g fill="#0b0820"><rect x="0" y="72" width="10" height="4"/><rect x="0" y="80" width="90" height="2"/><rect x="0" y="86" width="90" height="3"/></g>
<g fill="#151033"><rect x="0" y="74" width="14" height="44"/><rect x="14" y="86" width="10" height="32"/><rect x="66" y="70" width="12" height="48"/><rect x="78" y="82" width="12" height="36"/></g>
<g fill="#22e4ff" filter="url(#${k}gl)"><rect x="3" y="80" width="2" height="1.5"/><rect x="8" y="88" width="2" height="1.5"/><rect x="69" y="78" width="2" height="1.5"/><rect x="73" y="92" width="2" height="1.5"/><rect x="82" y="88" width="2" height="1.5"/></g>
<rect y="118" width="90" height="42" fill="#120a2e"/><g stroke="#ff2bd6" stroke-width=".5" filter="url(#${k}gl)" opacity=".85">
${[118, 122, 128, 136, 147, 160].map(y => `<line x1="0" y1="${y}" x2="90" y2="${y}"/>`).join("")}${[-60, -30, 0, 30, 60, 90, 120, 150].map(x => `<line x1="45" y1="118" x2="${x}" y2="160"/>`).join("")}</g>
<g filter="url(#${k}gl)" fill="#0b0820" stroke="#22e4ff" stroke-width="1"><ellipse cx="50" cy="129" rx="14" ry="16"/><circle cx="50" cy="104" r="13"/></g>
<circle cx="45" cy="103" r="2" fill="#22e4ff"/><circle cx="55" cy="103" r="2" fill="#22e4ff"/><path d="${SVGBITS.smile}" fill="none" stroke="#ff2bd6" stroke-width="1" stroke-linecap="round"/>`],
};

function styleSVG(st) {
  const k = "st" + st.id;
  const [defs, body] = SVGSTYLE[st.id](k);
  return `<svg viewBox="0 0 90 160" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg"><defs>${defs}</defs>${body}</svg>`;
}
