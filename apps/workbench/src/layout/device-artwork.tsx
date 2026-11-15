const outlines={
 aerial:<><path d="m94 68 52 40m0-40-52 40M106 76h28v24h-28z"/><ellipse cx="88" cy="62" rx="26" ry="9"/><ellipse cx="152" cy="62" rx="26" ry="9"/><ellipse cx="88" cy="114" rx="26" ry="9"/><ellipse cx="152" cy="114" rx="26" ry="9"/><path d="m112 100-8 20m24-20 8 20m-32 0h32"/></>,
 quadruped:<><path d="M72 71h68l16 13-12 25H75l-9-20zM144 76l12-19h24l7 25-28 6M80 109l-9 25 10 15m16-40-4 22 17 18m22-40 10 25-8 15m10-40 20 20-2 20M68 80 51 66"/><circle cx="175" cy="69" r="3"/><path d="M87 82h34m-32 9h18M76 149h12m17 0h12m12 0h12m15 0h12"/></>,
 wheeled:<><path d="M75 83h90l17 36H58zM84 83V64h70v19M108 64V42h25v22M58 119v14h124v-14M100 99h40"/><circle cx="79" cy="136" r="13"/><circle cx="161" cy="136" r="13"/><circle cx="120" cy="49" r="3"/></>,
 tracked:<><rect x="53" y="109" width="134" height="40" rx="20"/><circle cx="77" cy="129" r="12"/><circle cx="120" cy="129" r="12"/><circle cx="163" cy="129" r="12"/><path d="M74 108V75h91v33M94 75V55h47v20m-36-20V39h25v16M89 89h60"/></>,
 humanoid:<><rect x="105" y="31" width="30" height="28" rx="9"/><path d="M112 43h16m-14 16v12m12-12v12M99 72h42l-4 43h-34zM98 79 83 102l4 20m55-43 16 23-5 20M110 115l-6 30-8 12m34-42 7 30 8 12M89 157h17m30 0h17M112 87h16"/><circle cx="120" cy="98" r="4"/></>,
 other:<><path d="m120 37 53 30v60l-53 30-53-30V67zM67 67l53 30 53-30m-53 30v60M94 52l52 30m-52 0 52-30"/><circle cx="120" cy="97" r="18"/><path d="M67 97H44m129 0h23M120 37V20m0 137v17"/></>
};

/** Decorative equipment silhouettes, without implying a particular vendor or live state. */
export function DeviceArtwork({morphology}:{morphology:keyof typeof outlines}){
 return <svg className="recipient-device-artwork" viewBox="0 0 240 190" fill="none" aria-hidden="true" focusable="false">
  <g stroke="currentColor" strokeWidth="1" opacity=".3"><ellipse cx="120" cy="151" rx="99" ry="25"/><ellipse cx="120" cy="151" rx="80" ry="17"/><path d="M21 151h198M120 124v54M39 138l162 26m0-26L39 164"/><path strokeDasharray="3 7" d="M26 43v84m188-84v84M47 23h42m62 0h42"/></g>
  <g stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{outlines[morphology]}</g>
  <g fill="currentColor"><circle cx="26" cy="43" r="2"/><circle cx="214" cy="43" r="2"/><circle cx="47" cy="23" r="2"/><circle cx="193" cy="23" r="2"/></g>
 </svg>;
}
