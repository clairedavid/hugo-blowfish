(function () {
  'use strict';

  // Data comes from the page (see layouts/shortcodes/interactive-map.html),
  // which serialises data/interactive_map.json into #imap-data.
  const DATA = JSON.parse(document.getElementById('imap-data').textContent);
  const {W, H, LON0, LON1, LAT0, LAT1} = DATA.view;
  const LAND = DATA.land, LAKES = DATA.lakes, chapters = DATA.chapters;
  const proj = (lat, lon) => [ (lon - LON0) / (LON1 - LON0) * W, (LAT1 - lat) / (LAT1 - LAT0) * H ];

const SVGNS='http://www.w3.org/2000/svg';
const map=document.getElementById('map'),viewport=document.getElementById('viewport');
// viewBox comes from the data, so interactive_map.json stays the single source.
map.setAttribute('viewBox','0 0 '+W+' '+H);
const gLand=document.getElementById('land'),gLakes=document.getElementById('lakes'),gRoute=document.getElementById('route'),
      gHalos=document.getElementById('halos'),gPins=document.getElementById('pins'),gLabels=document.getElementById('labels');
const mapwrap=document.getElementById('mapwrap');
const rsMap=rough.svg(map);
LAND.forEach(d=>gLand.appendChild(rsMap.path(d,{fill:'#cfe6c2',fillStyle:'solid',stroke:'#8bb184',strokeWidth:1,roughness:1.4,bowing:1.1})));
LAKES.forEach(d=>gLakes.appendChild(rsMap.path(d,{fill:'#dcf0f7',fillStyle:'solid',stroke:'#a8cfe0',strokeWidth:.8,roughness:1.2,bowing:1})));

const tl=document.getElementById('timeline');let active=null,uid=0;
chapters.forEach((ch,i)=>{const b=document.createElement('button');b.className='yr';b.setAttribute('role','tab');
  b.innerHTML=`<span>${ch.yr}</span>`;b.addEventListener('click',()=>select(i));tl.appendChild(b);ch.el=b;});
function roundRectPath(x,y,w,h,r){return `M${x+r},${y} h${w-2*r} a${r},${r} 0 0 1 ${r},${r} v${h-2*r} a${r},${r} 0 0 1 ${-r},${r} h${-(w-2*r)} a${r},${r} 0 0 1 ${-r},${-r} v${-(h-2*r)} a${r},${r} 0 0 1 ${r},${-r} z`;}
function drawBoxes(){
  chapters.forEach(ch=>{ch.el.querySelectorAll('.box').forEach(s=>s.remove());
    const w=ch.el.offsetWidth,h=ch.el.offsetHeight;
    const svg=document.createElementNS(SVGNS,'svg');svg.setAttribute('class','box');svg.setAttribute('viewBox',`0 0 ${w} ${h}`);
    const r=10,x=2.5,y=2.5,ww=w-5,hh=h-5,d=roundRectPath(x,y,ww,hh,r);
    const cid='clip'+(uid++);const defs=document.createElementNS(SVGNS,'defs');
    const cp=document.createElementNS(SVGNS,'clipPath');cp.setAttribute('id',cid);
    const cpath=document.createElementNS(SVGNS,'path');cpath.setAttribute('d',d);cp.appendChild(cpath);defs.appendChild(cp);svg.appendChild(defs);
    const fill=document.createElementNS(SVGNS,'rect');fill.setAttribute('width',w);fill.setAttribute('height',h);
    fill.setAttribute('clip-path',`url(#${cid})`);fill.setAttribute('fill',ch._on?ch.col:'transparent');svg.appendChild(fill);ch._fill=fill;
    const rc=rough.svg(svg);
    svg.appendChild(rc.path(d,{roughness:.7,bowing:.6,stroke:getComputedStyle(document.getElementById('imap')).getPropertyValue('--boxstroke').trim(),strokeWidth:1.3,fill:'none',disableMultiStroke:true,preserveVertices:true}));
    ch.el.prepend(svg);});
}
const PIN_R=5.5;
function darker(hex,f=0.78){const n=parseInt(hex.slice(1),16);let r=(n>>16)&255,g=(n>>8)&255,b=n&255;
  r=Math.round(r*f);g=Math.round(g*f);b=Math.round(b*f);return '#'+((1<<24)+(r<<16)+(g<<8)+b).toString(16).slice(1);}
function labelXY(x,y,pos){switch(pos){
  case 'u':return[x,y-10,'middle'];
  case 'ul':return[x-8,y-9,'end'];
  case 'ur':return[x+8,y-9,'start'];
  case 'dl':return[x-8,y+18,'end'];
  case 'dr':return[x+8,y+18,'start'];
  default:return[x+9,y+5,'start'];}}
function circle(x,y,r,fill,stroke,sw){const c=document.createElementNS(SVGNS,'circle');
  c.setAttribute('cx',x);c.setAttribute('cy',y);c.setAttribute('r',r);c.setAttribute('fill',fill);
  c.setAttribute('stroke',stroke);c.setAttribute('stroke-width',sw);return c;}

/* smooth Catmull-Rom spline -> path d */
function splinePath(pts){
  if(pts.length<2)return '';
  let d=`M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  for(let i=0;i<pts.length-1;i++){
    const p0=pts[i-1]||pts[i],p1=pts[i],p2=pts[i+1],p3=pts[i+2]||pts[i+1];
    const c1x=p1[0]+(p2[0]-p0[0])/6, c1y=p1[1]+(p2[1]-p0[1])/6;
    const c2x=p2[0]-(p3[0]-p1[0])/6, c2y=p2[1]-(p3[1]-p1[1])/6;
    d+=` C${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d;
}
function drawRoute(ch){gRoute.innerHTML='';if(!ch.route)return;
  const pts=ch.route.map(ll=>proj(ll[0],ll[1]));
  const d=splinePath(pts);
  const pth=document.createElementNS(SVGNS,'path');
  pth.setAttribute('d',d);pth.setAttribute('class','route');
  pth.setAttribute('stroke',ch.col);pth.setAttribute('stroke-width',2.6);
  pth.setAttribute('stroke-dasharray','1 7');pth.style.opacity=.95;gRoute.appendChild(pth);
}

function drawChapter(i){
  gPins.innerHTML='';gLabels.innerHTML='';gHalos.innerHTML='';closePop();
  drawRoute(chapters[i]);
  const activeKeys=new Set(chapters[i].pins.map(p=>p.ll.join(',')));const seen=new Set();
  chapters.forEach(ch=>ch.pins.forEach(p=>{const key=p.ll.join(',');if(seen.has(key))return;seen.add(key);
    if(activeKeys.has(key))return;const [x,y]=proj(...p.ll);gPins.appendChild(circle(x,y,PIN_R,'#d8d3cc','#bdb7ae',1));}));
  const col=chapters[i].col;
  chapters[i].pins.forEach(p=>{const [x,y]=proj(...p.ll);
    const halo=circle(x,y,PIN_R,'none',col,1.4);halo.setAttribute('class','pin-halo');
    halo.style.animation='imap-pinpulse 2.4s ease-out infinite';gHalos.appendChild(halo);halo._base=PIN_R;
    const c=circle(x,y,PIN_R,col,darker(col),1.2);c.setAttribute('class','pin');
    c.addEventListener('click',(e)=>{e.stopPropagation();openPop(p,col,x,y);});
    const [lx,ly,anchor]=labelXY(x,y,p.pos);const t=document.createElementNS(SVGNS,'text');
    t.setAttribute('x',lx);t.setAttribute('y',ly);t.setAttribute('text-anchor',anchor);
    t.setAttribute('class','plabel');t.textContent=p.name;
    t.addEventListener('click',(e)=>{e.stopPropagation();openPop(p,col,x,y);});
    const enter=()=>{c.setAttribute('r',(PIN_R*1.55)/scale);t.style.fontWeight='700';};
    const leave=()=>{c.setAttribute('r',PIN_R/scale);t.style.fontWeight='500';};
    c.addEventListener('mouseenter',enter);c.addEventListener('mouseleave',leave);
    t.addEventListener('mouseenter',enter);t.addEventListener('mouseleave',leave);
    gPins.appendChild(c);gLabels.appendChild(t);});
  applyScale();
}
function applyScale(){const base=window.innerWidth<=640?30:17;
  document.querySelectorAll('.plabel').forEach(t=>t.style.fontSize=(base/scale)+'px');
  gPins.querySelectorAll('circle').forEach(c=>{c.setAttribute('r',PIN_R/scale);c.setAttribute('stroke-width',1.2/scale);});
  gHalos.querySelectorAll('circle').forEach(c=>{c.setAttribute('r',PIN_R/scale);c.setAttribute('stroke-width',1.4/scale);});
  gRoute.querySelectorAll('path').forEach(p=>{p.setAttribute('stroke-width',2.6/scale);p.setAttribute('stroke-dasharray',(1/scale)+' '+(7/scale));});
}
function select(i){active=i;document.getElementById('caption').textContent=chapters[i].cap;
  chapters.forEach((c,j)=>{const on=(j===i);c._on=on;c.el.classList.toggle('active',on);
    if(c._fill)c._fill.setAttribute('fill',on?c.col:'transparent');});drawChapter(i);}

/* ---- POPUP ---- */
const pop=document.getElementById('pop'),popbody=document.getElementById('popbody');
function closePop(){pop.classList.remove('on');}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function openPop(p,col,mx,my){
  let html=`<div class="ttl" style="color:${col}">${esc(p.name)}</div>`;
  (p.lines||[]).forEach(l=>html+=`<div class="ln">${esc(l)}</div>`);
  if(p.link)html+=`<div class="ln">${p.link.pre?esc(p.link.pre)+' ':''}<a href="${p.link.url}" target="_blank" rel="noopener">${esc(p.link.text)}</a></div>`;
  if(p.grey)html+=`<div class="grey">${esc(p.grey)}</div>`;
  popbody.innerHTML=html;
  pop.classList.add('on');
  positionPop(mx,my);
}
/* vertically centered, on the side opposite the pin; >=52% map width (desktop).
   mobile: near-full-width, vertical half opposite the pin, clear of the zoom button. */
function positionPop(mx,my){
  const r=map.getBoundingClientRect();
  const px=(mx*scale+tx)*r.width/W;
  const py=(my*scale+ty)*r.height/H;
  const MW=mapwrap.clientWidth,MH=mapwrap.clientHeight;
  const mobile=MW<=640;
  let cw;
  if(mobile){cw=MW-16;pop.style.width=cw+'px';pop.style.maxHeight=(MH-16)+'px';}
  else{cw=Math.min(Math.max(MW*0.52,500),MW-28);pop.style.width=cw+'px';pop.style.maxHeight='none';}
  const ch=pop.offsetHeight;
  const m=mobile?8:Math.max(14,MW*0.02);
  // vertical: place on the half OPPOSITE the pin (pin in top half -> card at bottom, and vice-versa)
  const cardBottom = py < MH/2;
  let top = cardBottom ? (MH-ch-m) : m;
  top=Math.max(m,Math.min(MH-ch-m,top));
  // horizontal: bottom cards go right (clear the Zoom-out button); top cards go opposite the pin
  let left;
  if(mobile){ left=8; }
  else if(cardBottom){ left = MW-cw-m; }
  else { left = (px>MW/2) ? m : (MW-cw-m); }
  pop.style.left=left+'px';pop.style.top=top+'px';
}
document.getElementById('popx').addEventListener('click',(e)=>{e.stopPropagation();closePop();});

/* pan/zoom */
// Phones open slightly pre-zoomed and centred, so pins are big enough to tap.
// Hit-testing is untouched: pins are real DOM nodes inside the transformed
// viewport, so the browser resolves taps; toMap() is only used for zoom
// anchoring and panning. Tune IMAP_PHONE_ZOOM by eye on a real device.
const IMAP_PHONE_ZOOM = 1.4;
const IMAP_IS_PHONE = window.matchMedia('(max-width:640px)').matches;
let scale = IMAP_IS_PHONE ? IMAP_PHONE_ZOOM : 1, tx = 0, ty = 0;
if (IMAP_IS_PHONE) { tx = (W - W * scale) / 2; ty = (H - H * scale) / 2; }
const MIN=1,MAX=6;
function clamp(){scale=Math.min(MAX,Math.max(MIN,scale));const minTx=W-W*scale,minTy=H-H*scale;tx=Math.min(0,Math.max(minTx,tx));ty=Math.min(0,Math.max(minTy,ty));}
function apply(){clamp();viewport.setAttribute('transform',`translate(${tx},${ty}) scale(${scale})`);applyScale();document.getElementById('zoomout').classList.toggle('active',scale>1.02);closePop();}
function toMap(cx,cy){const r=map.getBoundingClientRect();return [(cx-r.left)*W/r.width,(cy-r.top)*H/r.height];}
function zoomAt(cx,cy,factor){const [mx,my]=toMap(cx,cy);const old=scale;scale*=factor;scale=Math.min(MAX,Math.max(MIN,scale));const k=scale/old;tx=mx-((mx-tx)*k);ty=my-((my-ty)*k);apply();}
map.addEventListener('wheel',e=>{e.preventDefault();fade();zoomAt(e.clientX,e.clientY,e.deltaY<0?1.12:1/1.12);},{passive:false});
let dragging=false,lastX,lastY,moved=false,dsx=0,dsy=0;
map.addEventListener('pointerdown',e=>{if(e.pointerType==='touch')return;dragging=true;moved=false;lastX=e.clientX;lastY=e.clientY;dsx=e.clientX;dsy=e.clientY;});
map.addEventListener('pointermove',e=>{if(!dragging)return;const r=map.getBoundingClientRect();tx+=(e.clientX-lastX)*W/r.width;ty+=(e.clientY-lastY)*H/r.height;lastX=e.clientX;lastY=e.clientY;if(!moved&&Math.abs(e.clientX-dsx)+Math.abs(e.clientY-dsy)>6){moved=true;map.classList.add('grabbing');closePop();try{map.setPointerCapture(e.pointerId);}catch(_){}}apply();});
map.addEventListener('pointerup',()=>{dragging=false;map.classList.remove('grabbing');});
map.addEventListener('click',e=>{const tag=e.target.tagName;if(e.target===map||tag==='path')closePop();});
let touches=new Map(),pinchDist=0,lastPan=null;
map.addEventListener('touchstart',e=>{fade();for(const t of e.changedTouches)touches.set(t.identifier,{x:t.clientX,y:t.clientY});if(touches.size===1)lastPan=[...touches.values()][0];if(touches.size===2){pinchDist=0;lastPan=null;}},{passive:false});
map.addEventListener('touchmove',e=>{e.preventDefault();for(const t of e.changedTouches){if(touches.has(t.identifier))touches.set(t.identifier,{x:t.clientX,y:t.clientY});}const pts=[...touches.values()];if(pts.length===2){const d=Math.hypot(pts[0].x-pts[1].x,pts[0].y-pts[1].y);const mid={x:(pts[0].x+pts[1].x)/2,y:(pts[0].y+pts[1].y)/2};if(pinchDist)zoomAt(mid.x,mid.y,d/pinchDist);pinchDist=d;}else if(pts.length===1&&lastPan){const r=map.getBoundingClientRect();tx+=(pts[0].x-lastPan.x)*W/r.width;ty+=(pts[0].y-lastPan.y)*H/r.height;apply();lastPan=pts[0];}},{passive:false});
map.addEventListener('touchend',e=>{for(const t of e.changedTouches)touches.delete(t.identifier);const pts=[...touches.values()];pinchDist=0;lastPan=pts.length===1?pts[0]:null;});
document.getElementById('zoomout').addEventListener('click',()=>{if(scale<=1.02)return;scale=1;tx=0;ty=0;apply();});
let faded=false;function fade(){if(faded)return;faded=true;document.getElementById('ziphint').style.opacity=0;}

window.addEventListener('load',()=>{drawBoxes();select(chapters.length-1);apply();
  chapters[0].el.classList.add('nudge');setTimeout(()=>chapters[0].el.classList.remove('nudge'),1200);});
window.addEventListener('resize',()=>{drawBoxes();applyScale();closePop();});
if(window.matchMedia){window.matchMedia('(prefers-color-scheme:dark)').addEventListener('change',()=>drawBoxes());}
// The box stroke colour is baked into the rough.js SVG at draw time, so the
// boxes must be redrawn when Blowfish flips .dark on <html>.
new MutationObserver(()=>drawBoxes())
  .observe(document.documentElement,{attributes:true,attributeFilter:['class']});
})();
