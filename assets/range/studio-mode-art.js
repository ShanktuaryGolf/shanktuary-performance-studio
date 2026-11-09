/* Decorative practice diagrams. Real mode names, selection and scoring stay in
 * the production range controller; these paths carry no telemetry. */
(() => {
  const shapes = {
    practice: '<path d="M45 56Q110 -10 260 42"/><ellipse cx="260" cy="43" rx="22" ry="5"/><circle cx="45" cy="56" r="3" fill="white" stroke="none"/>',
    challenge: '<ellipse cx="145" cy="45" rx="43" ry="10"/><ellipse cx="145" cy="45" rx="23" ry="5"/><ellipse cx="65" cy="25" rx="18" ry="4"/><ellipse cx="240" cy="20" rx="15" ry="3"/><path class="gold" d="M145 45V4l19 7-19 7"/>',
    target_practice: '<ellipse cx="150" cy="43" rx="65" ry="13"/><ellipse cx="150" cy="43" rx="42" ry="8"/><path class="gold" d="M150 43V3l22 8-22 7"/>',
    ladder: '<path d="M20 54Q45 0 95 45M20 54Q80 -20 150 40M20 54Q120 -38 205 35M20 54Q155 -45 260 30"/><ellipse cx="95" cy="45" rx="12" ry="3"/><ellipse cx="150" cy="40" rx="12" ry="3"/><ellipse cx="205" cy="35" rx="12" ry="3"/><ellipse cx="260" cy="30" rx="12" ry="3"/>',
    'closest-pin': '<ellipse cx="150" cy="45" rx="74" ry="13"/><ellipse cx="150" cy="45" rx="47" ry="8"/><path class="gold" d="M150 45V4l22 7-22 8"/><circle cx="139" cy="43" r="3" fill="white" stroke="none"/>',
    'long-drive': '<path d="M15 55Q150 -38 280 35"/><ellipse cx="280" cy="36" rx="16" ry="4"/><circle cx="15" cy="55" r="3" fill="white" stroke="none"/>',
    grid: '<path opacity=".5" d="M55 54 100 10h100l45 44ZM80 32h140M150 10v44"/><ellipse cx="55" cy="54" rx="14" ry="3"/><ellipse cx="150" cy="54" rx="14" ry="3"/><ellipse cx="245" cy="54" rx="14" ry="3"/><ellipse cx="80" cy="32" rx="12" ry="3"/><ellipse cx="150" cy="32" rx="12" ry="3"/><ellipse cx="220" cy="32" rx="12" ry="3"/><ellipse cx="100" cy="10" rx="10" ry="2"/><ellipse cx="150" cy="10" rx="10" ry="2"/><ellipse cx="200" cy="10" rx="10" ry="2"/>',
    grid_custom: '<path stroke-dasharray="5 4" opacity=".5" d="m45 48 60-34 130-5 30 45Z"/><ellipse cx="45" cy="48" rx="24" ry="5"/><ellipse cx="105" cy="14" rx="18" ry="4"/><ellipse cx="235" cy="9" rx="16" ry="3"/><ellipse cx="265" cy="54" rx="26" ry="5"/>',
    combine: '<g class="gold"><circle cx="55" cy="30" r="21"/><circle cx="55" cy="30" r="13"/><circle cx="55" cy="30" r="5"/><path stroke-width="7" d="M135 49V35m14 14V22m14 27V9"/><path d="M235 52V6l29 11-29 11"/></g><path opacity=".4" d="M103 3v53M202 3v53"/>'
  };
  document.querySelectorAll('.game-mode-card').forEach(card => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'game-mode-art');
    svg.setAttribute('viewBox', '0 0 300 62');
    svg.setAttribute('aria-hidden', 'true');
    svg.innerHTML = shapes[card.dataset.mode] || '';
    card.appendChild(svg);
    card.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        card.click();
      }
    });
  });
})();
