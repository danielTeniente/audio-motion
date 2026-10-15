const $ = id => document.getElementById(id);
let token, selectedStyle = 'line', selectedPalette = 'aurora', file, busy = false, audioURL, temporaryPreview = false;
const symbols = ['∿','◎','♧','❄','◉','〰','◌','◇','◍'];
const title = s => s.replace(/\b\w/g, c => c.toUpperCase());
const wave = Array.from({length: 601}, (_, i) => {const x = 100+i; const envelope = Math.exp(-Math.pow((i-300)/145,2));return `${i?'L':'M'}${x},${195+Math.sin(i*.23)*Math.sin(i*.039)*55*envelope}`;}).join(' ');
document.querySelectorAll('.wave').forEach(p => p.setAttribute('d',wave));
function message(text='') {$('message').textContent=text;}
function update() {
  document.querySelectorAll('.style').forEach(b=>b.setAttribute('aria-pressed',b.dataset.value===selectedStyle));
  document.querySelectorAll('.palette').forEach(b=>b.setAttribute('aria-pressed',b.dataset.value===selectedPalette));
  $('brain-options').hidden=selectedStyle!=='brain sphere';
  $('stage-label').textContent=`${selectedStyle} / ${selectedPalette}`.toUpperCase();
  $('generate').disabled=busy || !file;
  $('preview').disabled=busy || !file;
}
function chooseFile(chosen) {
  if(busy || !chosen) return;
  if(chosen.size===0 || chosen.size>512*1024*1024) {message('Choose a nonempty audio file smaller than 512 MB.');return;}
  file=chosen;
  if(audioURL) URL.revokeObjectURL(audioURL);
  audioURL=URL.createObjectURL(file);
  $('audio-player').src=audioURL; $('audio-player').hidden=false;
  $('file-name').textContent=file.name;
  $('file-meta').textContent=`${(file.size/1024/1024).toFixed(1)} MB · click to replace`;
  message(); update();
}
$('audio').addEventListener('change',e=>chooseFile(e.target.files[0]));
['dragenter','dragover'].forEach(name=>$('drop').addEventListener(name,e=>{e.preventDefault();$('drop').classList.add('over');}));
['dragleave','drop'].forEach(name=>$('drop').addEventListener(name,e=>{e.preventDefault();$('drop').classList.remove('over');}));
$('drop').addEventListener('drop',e=>chooseFile(e.dataTransfer.files[0]));
function setBusy(value) {busy=value;document.querySelectorAll('form button, form select, form input').forEach(el=>el.disabled=value);update();}
function showStatus(job) {
  const active=['uploading','rendering'].includes(job.state);
  setBusy(active); $('rendering').hidden=!active;
  if(active) {
    $('render-title').textContent=job.state==='uploading'?'Uploading your audio':'Creating your video';
    $('render-detail').textContent=`${job.progress||0}% · ${job.state==='uploading'?'Getting your sound ready':'Turning sound into movement…'}`;
    $('progress').value=job.progress||0;
    $('caption').textContent='Keep the console open until your video is ready';
  } else if(job.state==='done') {
    $('empty').hidden=true; $('video').hidden=false;
    const url='/video?file='+encodeURIComponent(job.filename);
    if($('video').getAttribute('src')!==url) {$('video').src=url;$('video').load();}
    temporaryPreview=!!job.preview;
    $('download').hidden=temporaryPreview;$('download').download=job.filename;
    $('caption').textContent=temporaryPreview?'Temporary preview · replay as often as you like':'Ready · saved in your outputs folder';message();
  } else if(job.state==='error') {
    message(job.error || 'Could not create this video. Please try another audio file.');
    $('caption').textContent='Adjust your choices and try again';
  }
}
async function poll() {
  try {
    const response=await fetch('/api/status');if(!response.ok) throw new Error();
    const job=await response.json();showStatus(job);
    if(['uploading','rendering'].includes(job.state)) setTimeout(poll,800);
  } catch {setBusy(false);$('rendering').hidden=true;message('The studio is disconnected. Reopen Start Studio.bat if you closed the console, then refresh this page.');}
}
$('form').addEventListener('submit',async e=>{
  e.preventDefault();if(!file||busy)return;
  const preview=e.submitter?.id==='preview';
  temporaryPreview=preview;
  message();$('video').pause();$('audio-player').pause();$('video').hidden=true;$('empty').hidden=false;$('download').hidden=true;
  showStatus({state:'uploading',progress:0});
  const query=new URLSearchParams({preview:String(preview),style:selectedStyle,palette:selectedPalette,brain_mode:$('brain-mode').value});
  const xhr=new XMLHttpRequest();xhr.open('POST','/api/render?'+query);xhr.setRequestHeader('X-Studio-Token',token);
  xhr.upload.onprogress=e=>{if(e.lengthComputable){$('progress').value=e.loaded/e.total*100;$('render-detail').textContent=`${Math.round(e.loaded/e.total*100)}% · Uploading your audio`;}};
  xhr.onload=()=>{if(xhr.status===202)poll();else{let error='The upload failed. Please try again.';try{error=JSON.parse(xhr.responseText).error||error;}catch{}showStatus({state:'error',error});}};
  xhr.onerror=()=>showStatus({state:'error',error:'Connection lost. Make sure the studio console is open, then refresh.'});
  xhr.send(file);
});
(async()=>{
  try {
    const response=await fetch('/api/options');if(!response.ok)throw new Error();
    const options=await response.json();token=options.token;
    options.styles.forEach((style,i)=>{
      const b=document.createElement('button');b.type='button';b.className='style';b.dataset.value=style;
      const icon=document.createElement('span');icon.className='symbol';icon.textContent=symbols[i];icon.setAttribute('aria-hidden','true');
      const label=document.createElement('span');label.textContent=title(style);b.append(icon,label);
      b.onclick=()=>{selectedStyle=style;update();};$('styles').append(b);
    });
    Object.entries(options.palettes).forEach(([name,gradients])=>{
      const b=document.createElement('button');b.type='button';b.className='palette';b.dataset.value=name;
      const swatches=document.createElement('span');swatches.className='swatches';
      gradients.forEach(g=>{const dot=document.createElement('i');dot.style.background=`rgb(${g[1].join(',')})`;swatches.append(dot);});
      b.append(swatches,document.createTextNode(title(name)));
      b.onclick=()=>{selectedPalette=name;document.documentElement.style.setProperty('--accent',`rgb(${gradients[0][1].join(',')})`);document.documentElement.style.setProperty('--secondary',`rgb(${gradients[1][1].join(',')})`);update();};
      $('palettes').append(b);
    });
    update();showStatus(options.job);if(['uploading','rendering'].includes(options.job.state))poll();
  }catch{message('Could not connect to the studio. Open Start Studio.bat and use the browser window it opens.');}
})();

function discardPreview() {
  if(!temporaryPreview)return;
  temporaryPreview=false;
  $('video').pause();$('video').removeAttribute('src');$('video').load();
  $('video').hidden=true;$('empty').hidden=false;$('download').hidden=true;
  $('caption').textContent='Preview cleared · create another whenever you like';
  fetch('/api/discard-preview',{method:'POST',headers:{'X-Studio-Token':token},keepalive:true}).catch(()=>{});
}
window.addEventListener('pagehide',discardPreview);
