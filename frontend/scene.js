/* 3D illustration layers for TranscriptoGen AI (inline SVG, theme-aware via CSS variables).
   Each hero layer carries data-depth: the parallax controller moves it by mouse position. */
window.TG_SCENE = (() => {
  const defs = `
  <defs>
    <linearGradient id="gBody" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6D66F0"/><stop offset="1" stop-color="#3B34B8"/></linearGradient>
    <linearGradient id="gCap" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#F4F4FB"/><stop offset="1" stop-color="#C9C9DE"/></linearGradient>
    <linearGradient id="gDark" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3A3A4C"/><stop offset="1" stop-color="#15151C"/></linearGradient>
    <linearGradient id="gAmber" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FBBF24"/><stop offset="1" stop-color="#D97706"/></linearGradient>
    <linearGradient id="gGreen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#34D399"/><stop offset="1" stop-color="#059669"/></linearGradient>
    <linearGradient id="gPink" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#F472B6"/><stop offset="1" stop-color="#BE185D"/></linearGradient>
    <radialGradient id="gGlow" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="var(--accent)" stop-opacity="0.35"/><stop offset="1" stop-color="var(--accent)" stop-opacity="0"/></radialGradient>
    <pattern id="grille" width="8" height="8" patternUnits="userSpaceOnUse"><circle cx="4" cy="4" r="1.6" fill="#8E8EA8"/></pattern>
    <filter id="soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="6"/></filter>
    <filter id="shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="14" stdDeviation="12" flood-color="#0B0B12" flood-opacity="0.28"/></filter>
  </defs>`;

  /* ---------- hero scene: isometric microphone + waves + floating cards ---------- */
  const hero = `
<svg class="scene" viewBox="0 0 520 620" width="520" height="620" xmlns="http://www.w3.org/2000/svg" aria-label="3D microphone with sound waves, subtitle cards and language chips">
  ${defs}
  <g class="layer" data-depth="0.15">
    <ellipse cx="240" cy="540" rx="200" ry="60" fill="url(#gGlow)"/>
    <ellipse cx="240" cy="520" rx="150" ry="26" fill="none" stroke="var(--accent)" stroke-opacity="0.25" stroke-dasharray="6 10"/>
  </g>

  <!-- microphone -->
  <g class="layer float-a" data-depth="0.45" filter="url(#shadow)">
    <!-- base -->
    <ellipse cx="240" cy="500" rx="88" ry="26" fill="url(#gDark)"/>
    <path d="M152 500a88 26 0 0 0 176 0v-18a88 26 0 0 1-176 0z" fill="#25252F"/>
    <ellipse cx="240" cy="482" rx="88" ry="26" fill="url(#gBody)"/>
    <!-- stand -->
    <rect x="228" y="330" width="24" height="152" rx="12" fill="url(#gDark)"/>
    <rect x="234" y="330" width="6" height="152" rx="3" fill="#5B5B72" opacity="0.6"/>
    <!-- shock ring -->
    <ellipse cx="240" cy="332" rx="96" ry="30" fill="none" stroke="url(#gBody)" stroke-width="12"/>
    <ellipse cx="240" cy="332" rx="96" ry="30" fill="none" stroke="#FFFFFF" stroke-opacity="0.25" stroke-width="3"/>
    <!-- body -->
    <rect x="176" y="150" width="128" height="200" rx="64" fill="url(#gBody)"/>
    <rect x="186" y="160" width="40" height="180" rx="20" fill="#FFFFFF" opacity="0.10"/>
    <!-- capsule / grille -->
    <rect x="176" y="90" width="128" height="120" rx="60" fill="url(#gCap)"/>
    <rect x="182" y="96" width="116" height="108" rx="54" fill="url(#grille)"/>
    <rect x="176" y="150" width="128" height="14" fill="#3B34B8" opacity="0.9"/>
    <rect x="176" y="150" width="128" height="4" fill="#FFFFFF" opacity="0.5"/>
    <!-- LED -->
    <circle cx="240" cy="300" r="7" fill="#10B981"><animate attributeName="opacity" values="1;0.2;1" dur="1.4s" repeatCount="indefinite"/></circle>
  </g>

  <!-- sound waves -->
  <g class="layer" data-depth="0.7" fill="none" stroke-linecap="round">
    <path class="wave1" d="M330 120a95 95 0 0 1 0 140" stroke="var(--accent)" stroke-width="10" stroke-opacity="0.9"/>
    <path class="wave2" d="M360 90a140 140 0 0 1 0 200" stroke="var(--accent)" stroke-width="10" stroke-opacity="0.55"/>
    <path class="wave3" d="M390 60a185 185 0 0 1 0 260" stroke="var(--accent)" stroke-width="10" stroke-opacity="0.28"/>
    <path class="wave1" d="M150 120a95 95 0 0 0 0 140" stroke="var(--amber)" stroke-width="10" stroke-opacity="0.9"/>
    <path class="wave2" d="M120 90a140 140 0 0 0 0 200" stroke="var(--amber)" stroke-width="10" stroke-opacity="0.5"/>
  </g>

  <!-- floating subtitle card -->
  <g class="layer float-b" data-depth="1.0" filter="url(#shadow)">
    <g transform="translate(318 380) skewY(-6)">
      <rect width="180" height="92" rx="16" fill="var(--card)" stroke="var(--border)"/>
      <rect x="14" y="16" width="38" height="12" rx="6" fill="var(--accent)"/>
      <text x="60" y="26" font-family="Manrope, sans-serif" font-size="10" font-weight="700" fill="var(--faint)">00:01:12 → 00:01:17</text>
      <rect x="14" y="40" width="150" height="9" rx="4.5" fill="var(--text)" opacity="0.85"/>
      <rect x="14" y="56" width="110" height="9" rx="4.5" fill="var(--text)" opacity="0.55"/>
      <rect x="14" y="72" width="70" height="9" rx="4.5" fill="var(--text)" opacity="0.3"/>
    </g>
  </g>

  <!-- language chips -->
  <g class="layer float-c" data-depth="1.25" font-family="Manrope, sans-serif" font-weight="800" font-size="12">
    <g transform="translate(20 400)" filter="url(#shadow)">
      <rect width="92" height="34" rx="17" fill="var(--card)" stroke="var(--border)"/><circle cx="18" cy="17" r="5" fill="var(--accent)"/><text x="32" y="21" fill="var(--text)">English</text>
    </g>
    <g transform="translate(40 450)" filter="url(#shadow)">
      <rect width="78" height="34" rx="17" fill="var(--card)" stroke="var(--border)"/><circle cx="18" cy="17" r="5" fill="var(--amber)"/><text x="32" y="23" font-family="'Noto Nastaliq Urdu', serif" font-size="13" fill="var(--text)">اردو</text>
    </g>
    <g transform="translate(400 300)" filter="url(#shadow)">
      <rect width="86" height="34" rx="17" fill="var(--card)" stroke="var(--border)"/><circle cx="18" cy="17" r="5" fill="#10B981"/><text x="32" y="23" font-size="13" fill="var(--text)">العربية</text>
    </g>
    <!-- sparkle -->
    <g transform="translate(120 70)" fill="url(#gAmber)"><path class="spark" d="M16 0l4 12 12 4-12 4-4 12-4-12L0 16l12-4z"/></g>
  </g>
</svg>`;

  /* ---------- isometric step tiles ---------- */
  const tile = (inner, grad) => `
<svg class="tile-svg" viewBox="0 0 120 120" width="120" height="120" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  ${defs}
  <g filter="url(#shadow)">
    <path d="M60 22 108 46 60 70 12 46z" fill="url(#${grad})"/>
    <path d="M12 46v14l48 24V70z" fill="#0B0B12" opacity="0.28"/>
    <path d="M108 46v14L60 84V70z" fill="#0B0B12" opacity="0.14"/>
    <path d="M60 22 108 46 60 70 12 46z" fill="#FFFFFF" opacity="0.12"/>
  </g>
  <g class="tile-obj">${inner}</g>
</svg>`;

  const tiles = {
    upload: tile(`<path d="M42 44c-8 0-13-6-11-13 2-6 8-8 12-7 3-8 15-10 20-3 6-2 13 3 12 10 6 1 8 7 5 12-2 3-6 4-9 4H42z" fill="url(#gCap)" stroke="#B8B8D0"/><path d="M60 62V34" stroke="var(--accent)" stroke-width="6" stroke-linecap="round"/><path d="M48 44l12-12 12 12" fill="none" stroke="var(--accent)" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>`, "gBody"),
    slides: tile(`<g transform="translate(30 18) skewY(-12)"><rect x="12" y="10" width="56" height="40" rx="6" fill="#C9C9DE"/><rect x="4" y="2" width="56" height="40" rx="6" fill="url(#gCap)" stroke="#B8B8D0"/><path d="M12 32l12-12 8 8 8-10 12 14z" fill="url(#gAmber)"/><circle cx="18" cy="12" r="4" fill="var(--amber)"/></g>`, "gAmber"),
    subs: tile(`<g transform="translate(26 16) skewY(-12)"><rect x="4" y="2" width="68" height="46" rx="8" fill="url(#gCap)" stroke="#B8B8D0"/><rect x="12" y="12" width="46" height="7" rx="3.5" fill="#15151C" opacity="0.8"/><rect x="12" y="24" width="34" height="7" rx="3.5" fill="#15151C" opacity="0.5"/><circle cx="58" cy="34" r="9" fill="url(#gGreen)"/><path d="M55 29v10l8-5z" fill="#FFFFFF"/></g>`, "gGreen"),
    notes: tile(`<g transform="translate(30 12) skewY(-12)"><rect x="4" y="2" width="54" height="56" rx="7" fill="url(#gCap)" stroke="#B8B8D0"/><circle cx="14" cy="16" r="3" fill="url(#gPink)"/><rect x="21" y="13" width="28" height="6" rx="3" fill="#15151C" opacity="0.7"/><circle cx="14" cy="30" r="3" fill="url(#gPink)"/><rect x="21" y="27" width="22" height="6" rx="3" fill="#15151C" opacity="0.5"/><circle cx="14" cy="44" r="3" fill="url(#gPink)"/><rect x="21" y="41" width="26" height="6" rx="3" fill="#15151C" opacity="0.4"/><circle cx="54" cy="52" r="11" fill="url(#gGreen)"/><path d="M48 52l4 4 8-8" fill="none" stroke="#FFFFFF" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></g>`, "gPink"),
  };

  return { hero, tiles };
})();
