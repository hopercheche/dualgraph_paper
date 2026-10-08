
const search=document.querySelector('#paper-search'), filter=document.querySelector('#paper-filter');
function applyFilter(){document.querySelectorAll('.paper-card').forEach(x=>{x.classList.toggle('hidden',!(x.textContent.toLowerCase().includes((search?.value||'').toLowerCase())&&(!filter?.value||x.dataset.group===filter.value)));});}
search?.addEventListener('input',applyFilter);filter?.addEventListener('change',applyFilter);

// Navigation and diagram reading controls.
const bar = document.querySelector('.topbar');
if(bar){
 const line=document.createElement('div');line.className='progress-line';line.innerHTML='<span></span>';bar.append(line);
 const update=()=>{const max=document.documentElement.scrollHeight-innerHeight;line.firstElementChild.style.width=(max>0?scrollY/max*100:0)+'%';};
 addEventListener('scroll',update,{passive:true});update();
 const isMain=/\/index\.html$/.test(location.pathname)&&!location.pathname.endsWith('/evidence/index.html');
 if(isMain){
  const links=[...bar.querySelectorAll('nav a')];
  const sections=['problem','innovation','architecture','metrics','experiments','references'].map(id=>document.getElementById(id)).filter(Boolean);
  const mark=()=>{let current=sections[0];for(const s of sections){if(s.getBoundingClientRect().top<190)current=s;}links.forEach(a=>a.classList.toggle('active',a.hash==='#'+current?.id));};
  addEventListener('scroll',mark,{passive:true});mark();
 }
}
function openTargetDetails(){
 const id=decodeURIComponent(location.hash.slice(1));if(!id)return;
 const el=document.getElementById(id);if(!el)return;
 for(let d=el.closest('details');d;d=d.parentElement?.closest('details'))d.open=true;
 if(el.tagName==='DETAILS')el.open=true;
}
addEventListener('hashchange',openTargetDetails);openTargetDetails();

const zoomers=[...document.querySelectorAll('[data-zoom],.diagram img')];
if(zoomers.length){
 const dialog=document.createElement('dialog');dialog.className='figure-dialog';dialog.setAttribute('aria-label','Enlarged diagram');
 dialog.innerHTML='<div class="figure-toolbar"><b></b><button type="button" data-size="down" aria-label="Zoom out">−</button><button type="button" data-size="up" aria-label="Zoom in">＋</button><a target="_blank" rel="noopener">Open original figure</a><button type="button" data-close aria-label="Close enlarged figure">×</button></div><div class="figure-viewport"><img alt=""></div>';
 document.body.append(dialog);const image=dialog.querySelector('img');let width=1440;
 const show=(src,title)=>{image.src=src;image.alt=title;dialog.querySelector('b').textContent=title;dialog.querySelector('a').href=src;width=Math.max(1000,Math.min(1440,innerWidth-100));image.style.width=width+'px';dialog.showModal();dialog.querySelector('.figure-viewport').scrollTo(0,0);};
 zoomers.forEach(el=>el.addEventListener('click',ev=>{ev.preventDefault();show(el.dataset.zoom||el.src,el.dataset.title||el.alt||'Diagram');}));
 dialog.querySelector('[data-close]').addEventListener('click',()=>dialog.close());
 dialog.querySelector('[data-size="up"]').addEventListener('click',()=>{width=Math.min(3000,width*1.2);image.style.width=width+'px';});
 dialog.querySelector('[data-size="down"]').addEventListener('click',()=>{width=Math.max(1000,width/1.2);image.style.width=width+'px';});
 dialog.addEventListener('click',ev=>{if(ev.target===dialog)dialog.close();});
}
