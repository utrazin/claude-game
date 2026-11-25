export function build({ctx}) {
  ctx.fillStyle='#468848';
  for(const [x,y] of [[37,13],[65,5],[87,18]]) {ctx.beginPath();ctx.ellipse(x,y+13,9,22,(x-64)/35,0,Math.PI*2);ctx.fill();}
  ctx.fillStyle='#ed893d';ctx.strokeStyle='#9f4c28';ctx.lineWidth=4;
  ctx.beginPath();ctx.moveTo(37,43);ctx.quadraticCurveTo(63,31,90,44);ctx.quadraticCurveTo(91,72,55,119);ctx.quadraticCurveTo(31,82,37,43);ctx.closePath();ctx.fill();ctx.stroke();
  ctx.beginPath();ctx.moveTo(41,61);ctx.lineTo(59,65);ctx.moveTo(68,79);ctx.lineTo(79,76);ctx.stroke();
}
