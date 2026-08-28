const data = {
  xiaoman: {
    name:"小满", clock:"18:24", distance:36, light:"舒适", temp:24.6, humidity:48,
    focus:{today:52,week:286,month:1184}, eye:92, report:88, rounds:3, questions:4,
    reminder:[1,"16:32 提醒，已调整"], lights:[612,588,4], week:[32,48,41,56,38,45,52],
    reportLines:[["专注",91],["护眼",92],["任务",86]],
    qa:[["数学","为什么通分后分母要相同？","已理解",1],["数学","分数应用题先算什么？","需复习",0],["英语","quiet 怎么发音？","已理解",1],["语文","中心句在哪里？","已理解",1]]
  },
  lele: {
    name:"乐乐", clock:"11:08", distance:39, light:"右侧稍亮", temp:25.1, humidity:45,
    focus:{today:36,week:218,month:902}, eye:86, report:82, rounds:2, questions:3,
    reminder:[0,"今天没有距离提醒"], lights:[520,634,18], week:[25,34,28,41,30,24,36],
    reportLines:[["专注",78],["护眼",86],["任务",84]],
    qa:[["语文","主人公为什么生气？","已理解",1],["英语","through 怎么读？","需复习",0],["语文","迫不及待是什么意思？","已理解",1]]
  }
};

const state={child:"xiaoman",period:"today",theme:"orange"};
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
let seconds=18*60+24, toastTimer;
const text=(s,v)=>{const n=$(s);if(n)n.textContent=v};

function bars(values){
  const labels=["一","二","三","四","五","六","日"], max=Math.max(...values,60);
  $("#focusBars").innerHTML=values.map((v,i)=>`<div class="bar"><i style="height:${Math.max(8,v/max*100)}%" title="${v} 分钟"></i><span>${labels[i]}</span></div>`).join("");
}

function reportLines(items){
  $("#reportLines").innerHTML=items.map(x=>`<div class="report-line"><span>${x[0]}</span><i><b style="width:${x[1]}%"></b></i><strong>${x[1]}</strong></div>`).join("");
}

function questions(items){
  $("#qaList").innerHTML=items.map(x=>`<div class="qa-row"><span>${x[0]}</span><div><strong>${x[1]}</strong><small>${x[2]}</small></div><b class="${x[3]?"":"review"}">${x[3]?"已掌握":"复习"}</b></div>`).join("");
}

function render(){
  const d=data[state.child], f=d.focus[state.period];
  text("#childName",d.name);
  text("#heroFocus",f);
  text("#heroDate",state.period==="today"?"今日学习":state.period==="week"?"本周学习":"本月学习");
  text("#heroEye",d.eye);
  text("#heroReport",d.report);
  text("#liveClock",d.clock);
  text("#liveDistance",`${d.distance} cm`);
  text("#liveLight",d.light);
  text("#liveTemp",`${d.temp.toFixed(1)}°C`);
  text("#quickFocus",`${f} 分钟`);
  text("#quickDistance",`${d.distance} cm`);
  text("#quickQuestions",`${d.questions} 个`);
  text("#quickEnvironment","舒适");
  text("#eyeStatus",d.distance>=33&&d.distance<=45?"正常":"需调整");
  $("#distanceValue").innerHTML=`${d.distance}<small>cm</small>`;
  $("#distanceMarker").style.left=`${Math.min(90,Math.max(10,(d.distance-20)/35*100))}%`;
  $("#reminderCount").innerHTML=`${d.reminder[0]}<small>次</small>`;
  text("#reminderText",d.reminder[1]);
  text("#studyStatus",d.light==="舒适"?"稳定":"关注光线");
  text("#focusTotal",`${f} 分钟`);
  text("#roundCount",`${d.rounds} 轮`);
  text("#longestFocus",state.child==="xiaoman"?"最长 24 分钟":"最长 21 分钟");
  text("#lightState",d.light);
  text("#leftLight",d.lights[0]);
  text("#rightLight",d.lights[1]);
  text("#lightDifference",`${d.lights[2]}%`);
  $("#lightBalance").style.left=`${50+Math.min(30,d.lights[2]/2)}%`;
  text("#reportScore",d.report);
  text("#qaCount",`${d.questions} 个`);
  $("#temperature").innerHTML=`${d.temp.toFixed(1)}<small>°C</small>`;
  $("#humidity").innerHTML=`${d.humidity}<small>%</small>`;
  bars(d.week);
  reportLines(d.reportLines);
  questions(d.qa);
}

function toast(message){
  const n=$("#toast");
  n.textContent=message;
  n.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer=setTimeout(()=>n.classList.remove("show"),2200);
}

$$('[data-scroll]').forEach(btn=>btn.onclick=()=>{
  const target=document.getElementById(btn.dataset.scroll);
  window.scrollTo({top:target.getBoundingClientRect().top+window.scrollY-20,behavior:"smooth"});
  $$('.nav').forEach(n=>n.classList.toggle('active',n===btn));
  document.body.classList.remove('menu-open');
});

$$('.child').forEach(btn=>btn.onclick=()=>{
  state.child=btn.dataset.child;
  seconds=state.child==="xiaoman"?1104:668;
  $$('.child').forEach(n=>n.classList.toggle('active',n===btn));
  render();
});

$$('.period').forEach(btn=>btn.onclick=()=>{
  state.period=btn.dataset.period;
  $$('.period').forEach(n=>n.classList.toggle('active',n===btn));
  render();
});

$('#themeButton').onclick=()=>{
  state.theme=state.theme==="orange"?"pink":"orange";
  document.body.dataset.theme=state.theme;
  $('#themeButton span').textContent=state.theme==="orange"?"橙白":"粉白";
};

$('#exportButton').onclick=()=>toast('周报已生成');
$$('.switch-card input').forEach(x=>x.onchange=()=>toast(x.checked?'已开启':'已关闭'));
$('#menuButton').onclick=()=>document.body.classList.add('menu-open');
$('#backdrop').onclick=()=>document.body.classList.remove('menu-open');
setInterval(()=>{
  seconds++;
  text('#liveClock',`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`);
},1000);

render();
