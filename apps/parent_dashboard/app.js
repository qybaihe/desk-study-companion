const demoData = {
  xiaoman: {
    name:"小满", clock:1104, distance:36, light:"舒适", temperature:24.6, humidity:48,
    focus:{today:52,week:286,month:1184}, eye:92, report:88, rounds:3, questions:4,
    reminder:[1,"提醒后恢复正常"], lights:[612,588,4], week:[32,48,41,56,38,45,52],
    reportBars:[["专注",91],["护眼",92],["任务",86]],
    qa:[["数学","为什么通分后分母要相同？","已理解",1],["数学","分数应用题先算什么？","需复习",0],["英语","quiet 怎么发音？","已理解",1],["语文","中心句在哪里？","已理解",1]],
    subjects:[["数学",75],["英语",16],["语文",9]],
    art:{overview:"overview-family-girl.png",eyes:"eye-distance-sheep.png",study:"study-focus.png",qa:"questions-sheep.png",environment:"environment-sheep.png"}
  },
  lele: {
    name:"乐乐", clock:668, distance:39, light:"右侧稍亮", temperature:25.1, humidity:45,
    focus:{today:36,week:218,month:902}, eye:86, report:82, rounds:2, questions:3,
    reminder:[0,"今天没有提醒"], lights:[520,634,18], week:[25,34,28,41,30,24,36],
    reportBars:[["专注",78],["护眼",86],["任务",84]],
    qa:[["语文","主人公为什么生气？","已理解",1],["英语","through 怎么读？","需复习",0],["语文","迫不及待是什么意思？","已理解",1]],
    subjects:[["语文",66],["英语",34],["数学",0]],
    art:{overview:"overview-family.png",eyes:"eye-distance-boy-sheep.png",study:"study-focus-boy.png",qa:"questions-boy-sheep.png",environment:"environment-boy-sheep.png"}
  }
};

const titles={overview:"总览",eyes:"护眼",study:"学习状态",qa:"提问",environment:"环境"};
const petStates={
  overview:{image:"pet-pink.png",label:"陪伴中"},
  eyes:{image:"pet-green.png",label:"护眼正常"},
  study:{image:"pet-red.png",label:"专注中"},
  qa:{image:"pet-pink.png",label:"有问必答"},
  environment:{image:"pet-green.png",label:"环境舒适"}
};
const state={child:"xiaoman",period:"today",page:"overview",theme:"orange"};
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
let liveSeconds=demoData.xiaoman.clock, toastTimer;
const setText=(selector,value)=>{const node=$(selector);if(node)node.textContent=value};

function renderWeek(selector,values){
  const labels=["一","二","三","四","五","六","日"],max=Math.max(60,...values);
  $(selector).innerHTML=values.map((value,index)=>`<div class="week-bar"><i style="height:${Math.max(8,value/max*100)}%" title="${value} 分钟"></i><span>${labels[index]}</span></div>`).join("");
}

function renderMiniBars(values){
  $("#miniFocusBars").innerHTML=values.slice(-5).map(value=>`<i style="height:${Math.max(15,value/60*100)}%"></i>`).join("");
}

function renderReport(items){
  $("#reportBars").innerHTML=items.map(item=>`<div class="report-row"><span>${item[0]}</span><i><b style="width:${item[1]}%"></b></i><strong>${item[1]}</strong></div>`).join("");
}

function renderQuestions(items){
  $("#qaList").innerHTML=items.map(item=>`<div class="qa-row"><span>${item[0]}</span><div><strong>${item[1]}</strong><small>${item[2]}</small></div><b class="${item[3]?"":"review"}">${item[3]?"掌握":"复习"}</b></div>`).join("");
}

function renderSubjects(items){
  $("#subjectBars").innerHTML=items.map(item=>`<div class="subject-row"><div><span>${item[0]}</span><strong>${item[1]}%</strong></div><div><i style="width:${item[1]}%"></i></div></div>`).join("");
  setText("#topSubject",`${items[0][0]} ${items[0][1]}%`);
  setText("#subjectDonutValue",items[0][1]);
  $("#subjectDonut").style.setProperty("--donut-value",`${items[0][1]}%`);
}

function renderAlertBars(count){
  const values=count?[8,13,7,26,10,6,4]:[4,5,4,6,4,5,4];
  $("#alertBars").innerHTML=values.map(value=>`<i style="height:${value}px"></i>`).join("");
}

function renderIllustrations(d){
  const base="./assets/illustrations/",version="?v=8";
  $("#sidebarIllustration").src=base+d.art.overview+version;
  $("#overviewIllustration").src=base+d.art.overview+version;
  $("#eyeIllustration").src=base+d.art.eyes+version;
  $("#studyIllustration").src=base+d.art.study+version;
  $("#qaIllustration").src=base+d.art.qa+version;
  $("#environmentIllustration").src=base+d.art.environment+version;
}

function updatePet(){
  const pet=petStates[state.page],d=demoData[state.child];
  $("#petAvatar").src=`./assets/pet/${pet.image}?v=5`;
  setText("#petStatusText",pet.label);
  const avatar=$("#petAvatar");
  avatar.classList.remove("pet-pop");
  void avatar.offsetWidth;
  avatar.classList.add("pet-pop");
  $("#petControl").dataset.message=state.page==="study"
    ?`${d.name}已专注 ${d.focus[state.period]} 分钟`
    :state.page==="eyes"?`当前距离 ${d.distance} cm`
    :state.page==="qa"?`今天记录 ${d.questions} 个问题`
    :state.page==="environment"?`${d.temperature.toFixed(1)}°C · 湿度 ${d.humidity}%`
    :`${d.name}正在学习`;
}

function render(){
  const d=demoData[state.child], focus=d.focus[state.period];
  setText("#overviewName",d.name);
  $("#overviewFocus").innerHTML=`${focus}<small>分钟</small>`;
  $("#overviewEye").innerHTML=`${d.eye}<small>分</small>`;
  $("#overviewQuestions").innerHTML=`${d.questions}<small>个</small>`;
  setText("#overviewEnvironment","舒适");
  $("#weekFocus").innerHTML=`${d.focus.week}<small>分钟</small>`;
  setText("#overviewClock",formatClock(liveSeconds));
  setText("#overviewDistance",`${d.distance} cm`);
  setText("#overviewLight",`光线${d.light}`);

  setText("#eyeDistance",d.distance);
  setText("#eyeStatus",d.distance>=33&&d.distance<=45?"正常":"需调整");
  $("#eyeScore").innerHTML=`${d.eye}<small>分</small>`;
  setText("#reminderCount",`${d.reminder[0]} 次`);
  setText("#reminderText",d.reminder[1]);
  $("#distanceMarker").style.left=`${Math.max(10,Math.min(90,(d.distance-20)/35*100))}%`;
  setText("#eyeRingValue",d.eye);
  $("#eyeRing").style.setProperty("--ring-value",`${d.eye}%`);

  setText("#studyFocus",focus);
  setText("#studyRounds",d.rounds);
  setText("#studyReport",d.report);
  setText("#studyLongest",state.child==="xiaoman"?"最长 24 分钟":"最长 21 分钟");
  setText("#studyLightState",d.light);
  setText("#lightDifference",`差异 ${d.lights[2]}%`);
  setText("#leftLight",d.lights[0]);
  setText("#rightLight",d.lights[1]);
  const lightDirection=d.lights[1]>=d.lights[0]?1:-1;
  $("#lightMarker").style.left=`${50+lightDirection*Math.min(30,d.lights[2]/2)}%`;
  setText("#reportScore",d.report);

  setText("#questionCount",d.questions);
  $("#temperature").innerHTML=`${d.temperature.toFixed(1)}<small>°C</small>`;
  $("#humidity").innerHTML=`${d.humidity}<small>%</small>`;

  renderWeek("#weekChart",d.week);
  renderWeek("#studyChart",d.week);
  renderMiniBars(d.week);
  renderReport(d.reportBars);
  renderQuestions(d.qa);
  renderSubjects(d.subjects);
  renderAlertBars(d.reminder[0]);
  renderIllustrations(d);
  updatePet();
}

function formatClock(seconds){
  return `${String(Math.floor(seconds/60)).padStart(2,"0")}:${String(seconds%60).padStart(2,"0")}`;
}

function showPage(page){
  state.page=page;
  $$(".page").forEach(node=>node.classList.toggle("active",node.dataset.page===page));
  $$(".nav-item").forEach(node=>node.classList.toggle("active",node.dataset.pageTarget===page));
  setText("#pageTitle",titles[page]);
  updatePet();
  document.body.classList.remove("menu-open");
}

function toast(message){
  const node=$("#toast");
  node.textContent=message;
  node.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer=setTimeout(()=>node.classList.remove("show"),2200);
}

$$('[data-page-target]').forEach(button=>button.addEventListener("click",()=>showPage(button.dataset.pageTarget)));
$$('.child').forEach(button=>button.addEventListener("click",()=>{
  state.child=button.dataset.child;
  liveSeconds=demoData[state.child].clock;
  $$('.child').forEach(node=>node.classList.toggle("active",node===button));
  render();
}));
$$('.period').forEach(button=>button.addEventListener("click",()=>{
  state.period=button.dataset.period;
  $$('.period').forEach(node=>node.classList.toggle("active",node===button));
  render();
}));
$('#themeButton').addEventListener("click",()=>{
  state.theme=state.theme==="orange"?"pink":"orange";
  document.body.dataset.theme=state.theme;
  $('#themeButton span').textContent=state.theme==="orange"?"杏白":"粉白";
});
$('#petControl').addEventListener("click",()=>toast($('#petControl').dataset.message));
$('#exportButton').addEventListener("click",()=>toast("周报已生成"));
$$('.switches input').forEach(input=>input.addEventListener("change",()=>toast(input.checked?"已开启":"已关闭")));
$('#mobileMenu').addEventListener("click",()=>document.body.classList.add("menu-open"));
$('#backdrop').addEventListener("click",()=>document.body.classList.remove("menu-open"));

setInterval(()=>{
  liveSeconds++;
  setText("#overviewClock",formatClock(liveSeconds));
},1000);

render();
