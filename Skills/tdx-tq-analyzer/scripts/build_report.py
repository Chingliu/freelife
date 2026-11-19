# -*- coding: utf-8 -*-
"""
Build a self-contained offline HTML report from metrics + chart JSON.
Pure Python. Charts are rendered with inline SVG and vanilla JavaScript; no network dependency.

Usage:
    python build_report.py <METRICS_JSON> <CHART_JSON> <OUTPUT_HTML>
"""
import json
import sys

TPL = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>

<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f5f6f8;color:#1f2329;line-height:1.6;padding:28px 16px}
.wrap{max-width:1180px;margin:0 auto}
.header{border-bottom:2px solid #d93025;padding-bottom:16px;margin-bottom:24px}
.header h1{font-size:24px;font-weight:600}
.header .sub{color:#6b7280;font-size:13px;margin-top:6px}
.tag{display:inline-block;background:#fdecea;color:#c5221f;padding:2px 9px;border-radius:4px;font-size:12px;margin-left:8px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:20px 22px;margin-bottom:18px}
.card h2{font-size:17px;font-weight:600;margin-bottom:14px;border-left:4px solid #d93025;padding-left:10px}
.tldr{background:#fffbf0;border:1px solid #fcd9a8}
.tldr ul{margin-left:20px}.tldr li{margin-bottom:8px;font-size:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:4px}
.kpi{background:#fafafa;border:1px solid #eee;border-radius:8px;padding:13px}
.kpi .l{font-size:12px;color:#6b7280}.kpi .v{font-size:21px;font-weight:600;margin-top:3px}
.red{color:#d93025}.green{color:#0f9d58}.gray{color:#6b7280}
.chart{width:100%;height:380px}.chart-sm{width:100%;height:300px}
table{width:100%;border-collapse:collapse;font-size:12px;margin-top:10px}
th,td{padding:7px 8px;border-bottom:1px solid #eef0f2;text-align:right}
th{background:#f8f9fa;color:#4b5563;font-weight:500}
th:first-child,td:first-child{text-align:left}
.note{font-size:12px;color:#6b7280;margin-top:10px;line-height:1.7}
.disclaimer{background:#f3f4f6;border-radius:8px;padding:14px 16px;font-size:12px;color:#4b5563;margin-top:20px}
.tabs{display:flex;gap:6px;margin-bottom:10px}
.tab{padding:5px 14px;border:1px solid #d1d5db;border-radius:6px;background:#fff;cursor:pointer;font-size:13px}
.tab.on{background:#d93025;color:#fff;border-color:#d93025}
.hidden{display:none}
.veto{background:#fdecea;color:#c5221f;border:1px solid #f5c6c6;border-radius:8px;padding:12px 14px;font-size:13px;margin-bottom:12px}
.pass{background:#e6f4ea;color:#137333;border:1px solid #b7e1c1;border-radius:8px;padding:12px 14px;font-size:13px;margin-bottom:12px}
.st{display:inline-block;padding:1px 7px;border-radius:4px;font-size:11px;font-weight:500}
.st-ok{background:#e6f4ea;color:#137333}.st-no{background:#fdecea;color:#c5221f}
.st-mid{background:#fef7e0;color:#a15c00}.st-na{background:#f3f4f6;color:#6b7280}
.na{color:#6b7280;font-style:italic}
.explain{background:#f0f6ff;border:1px solid #c3d5f5;border-radius:8px;padding:16px 18px;margin-top:14px}
.explain h3{font-size:14px;font-weight:600;color:#1a3a6b;margin-bottom:10px}
.explain p{font-size:13px;color:#2d3a4a;margin-bottom:8px;line-height:1.8}
.explain .formula{background:#fff;border:1px solid #d0dff5;border-radius:6px;padding:8px 12px;font-family:monospace;font-size:13px;color:#1a3a6b;margin:8px 0}
.explain .result{font-weight:600;color:#c5221f}
.bc-intro{background:#f8f9fa;border:1px solid #e5e7eb;border-radius:8px;padding:16px 18px;margin-bottom:14px}
.bc-intro h3{font-size:14px;font-weight:600;color:#374151;margin-bottom:10px}
.bc-intro ol{font-size:13px;color:#374151;padding-left:20px;line-height:1.9}
.bc-intro ol li{margin-bottom:4px}
.bc-intro .formula{background:#fff;border:1px solid #d1d5db;border-radius:6px;padding:6px 12px;font-family:monospace;font-size:12px;color:#1f2329;margin:6px 0}
.course-chapter{border-top:1px solid #e5e7eb;padding:20px 0}.course-chapter h3{font-size:17px;margin-bottom:8px;color:#24344d}
.course-chapter h4{font-size:14px;margin:12px 0 6px}.course-chapter p,.course-chapter li{font-size:13px;line-height:1.85}
.course-goal{color:#475467;margin-bottom:10px}.course-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
.course-grid>div{background:#f8fafc;border:1px solid #e5e7eb;border-radius:8px;padding:13px}
.course-formula{background:#fff;border:1px solid #d1d5db;border-radius:6px;padding:9px;margin-top:8px;font:12px/1.7 monospace;overflow-wrap:anywhere}
.course-chapter ol{padding-left:22px}.course-chapter li{margin:4px 0}.course-caution{background:#fff8e8;border-left:3px solid #d99b2b;padding:9px 12px;margin-top:10px}
.course-quiz{background:#f0f6ff;border:1px solid #c3d5f5;border-radius:8px;padding:12px;margin-top:12px;font-size:13px}
.quiz-options{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:8px}.quiz-options button{border:1px solid #9db6dc;background:white;border-radius:6px;padding:6px 10px;cursor:pointer}
.quiz-answer{color:#2459a6;font-weight:600}
</style>
</head>
<body>
<div class="wrap">
<div class="header">
<h1>__TITLE__ <span class="tag">__TAG__</span></h1>
<div class="sub">数据来源：通达信金融终端官方 TQ 接口（tqcenter）｜快照时点：__ASOF__ __SNAPTIME__｜标的：__NAME__（__CODE__）</div>
</div>

<div class="card tldr">
<h2>核心结论</h2>
<ul>__TLDR__</ul>
</div>

<div class="card">
<h2>实时快照关键指标</h2>
<div class="grid">__KPIS__</div>
<div class="note">__SNAPNOTE__</div>
</div>

<div class="card">
<h2>价格与成交量（近 60 交易日）</h2>
<div class="tabs"><div class="tab on" onclick="sw('k',this)">图</div><div class="tab" onclick="sw('kt',this)">表</div></div>
<div id="k"><div id="chart1" class="chart"></div></div>
<div id="kt" class="hidden"><table><thead><tr><th>日期</th><th>收盘</th><th>成交量(亿股)</th></tr></thead><tbody>__TABLE__</tbody></table></div>
<div class="note">红涨绿跌（A 股习惯）｜成交量单位：亿股｜数据来源：通达信 TQ 日 K 线，截至 __ASOF__。</div>
</div>

<div class="card">
<h2>量能结构分析</h2>
<div id="chart2" class="chart-sm"></div>
<div class="note">__VOLNOTE__</div>
<div class="explain">
<h3>📖 量能 & 量比是什么？怎么算出来的？</h3>
<p><b>成交量</b>：某一天成交的股票数量（单位：股/万手）。成交量越大，代表当天市场参与越活跃，价格变动的"底气"越足。</p>
<p><b>量比（Volume Ratio）</b>：今天的成交量 ÷ 最近 N 天的平均成交量，用来判断今天比平时放大还是缩小了几倍。</p>
<div class="formula">量比(5日) = 今日成交量 ÷ 前5日平均成交量<br>量比(20日) = 今日成交量 ÷ 前20日平均成交量</div>
<p><b>代入本次数据（510330 沪深300ETF，__ASOF__）：</b></p>
<p>· 今日成交 <b>__TODAY_YI__ 亿股</b>（前一日 __PREV_YI__ 亿股）<br>
· 前5日均量 __V5_YI__ 亿股 → 量比(5日) = <b>__VR5__</b>（>1.5 为明显放量，<0.7 为缩量）<br>
· 前20日均量 __V20_YI__ 亿股 → 量比(20日) = <b>__VR20__</b><br>
· 60日中位量 __MED60_YI__ 亿股，今日量是60日中位量的约 <b>__VR_MED60__</b> 倍</p>
<p><b>上涨/下跌日均量比</b>：近20个完整交易日中，上涨日的平均成交量 ÷ 下跌日的平均成交量。比值 >1 说明涨的时候量比跌的时候大，量能结构偏多；<1 则偏空。</p>
<div class="formula">上涨日均量 __UPV_YI__ 亿 ÷ 下跌日均量 __DNV_YI__ 亿 = <b>__UPDOWN_RATIO__</b></div>
<p class="note" style="margin-top:8px">⚠️ 盘中数据：今日成交量尚未收盘定局，量比在收盘后会进一步变化。宽基 ETF 的巨量常含一级申赎与做市商对冲，不等于方向性下注。</p>
</div>
</div>

<div class="card">
<h2>资金流入流出</h2>
<div id="chart3" class="chart-sm"></div>
<div class="note">__FLOWNOTE__</div>
<div class="explain">
<h3>📖 内/外盘 & CMF 是什么？怎么算出来的？</h3>
<p><b>内盘 / 外盘</b>：交易所每笔成交都以买价或卖价撮合。以卖价成交（主动买入）计为<b>外盘</b>；以买价成交（主动卖出）计为<b>内盘</b>。外盘占比 >55% 说明主动买盘占优，<45% 则主动卖盘占优。</p>
<div class="formula">外盘占比 = 外盘成交量 ÷ (外盘 + 内盘) × 100%<br>= __OUTSIDE_WAN__ 万手 ÷ (__OUTSIDE_WAN__ + __INSIDE_WAN__) 万手 = <b>__OUTSIDE_RATIO__%</b></div>
<p><b>净主动买入估算</b>：（外盘 − 内盘）÷ 总成交量 × 今日成交额，是统计推断值，非实际机构资金流。</p>
<div class="formula">净主动买入 = (__OUTSIDE__ − __INSIDE__) ÷ __VOL_LOTS__ × __AMOUNT__ 亿 ≈ <b>__NET_ACTIVE_YI__ 亿元</b></div>
<p><b>CMF（Chaikin Money Flow，蔡金资金流）</b>：衡量近20日资金流入强度的综合指标。它把每天的量价关系压缩成一个"有向成交量"，再求20日累积。</p>
<div class="formula">单日 MFV = [(收盘价 − 最低价) − (最高价 − 收盘价)] ÷ (最高价 − 最低价) × 当日成交量<br>
CMF(20日) = 近20日 MFV 之和 ÷ 近20日成交量之和<br>
= __CMF_MFV_SUM_E__ ÷ __CMF_VOL_SUM_E__ = <b>__CMF20__</b></div>
<p>· MFV > 0：收盘靠近最高价，资金主动买入；MFV < 0：收盘靠近最低价，资金主动卖出。<br>
· CMF > +0.05：中期净流入；CMF < −0.05：中期净流出；之间为中性。<br>
· <b>本次结果：CMF = <span class="result">__CMF20__</span>，属于<span class="result">__CMF_DESC__</span>。</b></p>
<p class="note" style="margin-top:8px">⚠️ 内/外盘与 CMF 均为基于成交数据的统计推断，不等同于真实主力账户进出。ETF 申赎数据需基金公司公告确认，本报告未包含。</p>
</div>
</div>

<div class="card">
<h2>买入依据核对（研究观察，非买入建议）</h2>
<div class="bc-intro">
<h3>📖 这份推导是怎么做出来的？</h3>
<ol>
<li><b>第一步：硬否决检查</b>——先查有没有必须先排除的情况。本次共检查 3 项：① 趋势与中期资金是否同时转空（价格同时跌破 MA20/MA60 且 CMF &lt; −0.05）；② 价格是否贴近压力位且量能不支持；③ 数据是否够 60 根 K 线。有任意一项触发则直接判定"不成立"，不再看后续。本次触发 <b>__BC_VETO_N__</b> 项。</li>
<li><b>第二步：四维度打分</b>——逐项检查是否有数据支撑，不做多数票表决。
  <br>· <b>趋势位置</b>：现价 vs MA5/MA20/MA60。价格在均线之上 = 支持；之下 = 不支持。
  <br>· <b>量能确认</b>：量比(20日) ≥ 0.8 且 上涨/下跌日均量比 > 1.1 → 支持；量比 > 1.5 且价格在 MA20 下方（放量滞涨）→ 不支持。
  <br>· <b>资金确认</b>：CMF20 > +0.05 且外盘占比 > 50% → 支持；CMF20 < −0.05 → 不支持。
  <br>· <b>位置与风险回报</b>：支撑位到现价的距离 ÷ 现价到压力位的距离 = R:R（风险回报比）。≥ 1.5 = 合理；&lt; 1 = 偏贵。
</li>
<li><b>第三步：综合定档</b>——无否决且三个维度均支持 + R:R ≥ 1.5 → "关注"；无否决且两个维度支持 → "试探"；否则 → "观望"。本次档位：<b>__BC_TIER__</b>。</li>
<li><b>第四步：证据等级</b>——数据源单一（通达信 TQ），无样本外回测与跨标的验证，故上限为 <b>C 级</b>（有否决时降为 D）。</li>
<li><b>第五步：触发/止损/观察点</b>——所有价格均取自实际 K 线，不预测目标价。触发 = 什么条件满足时这套逻辑开始生效；止损 = 什么条件满足时逻辑失效；观察点 = 需要持续跟踪的指标。</li>
</ol>
</div>
<div class="grid" style="margin-bottom:14px">
<div class="kpi"><div class="l">核对档位</div><div class="v">__BC_TIER__</div></div>
<div class="kpi"><div class="l">证据等级</div><div class="v">__BC_GRADE__</div></div>
<div class="kpi"><div class="l">硬否决项</div><div class="v">__BC_VETO_N__</div></div>
</div>
__BC_GATE__
<table>
<thead><tr><th style="width:16%">维度</th><th style="width:12%">结论</th><th>依据（均来自 TQ 数据或明确标注未评估）</th></tr></thead>
<tbody>__BC_ROWS__</tbody>
</table>
<div class="note">__BC_GRADE_BASIS__</div>
<h3 style="font-size:14px;font-weight:600;margin:18px 0 8px;color:#374151">触发 / 止损 / 观察点（三元组）</h3>
<table>
<tbody>
<tr><th style="width:16%">触发条件</th><td style="text-align:left">__BC_TRIGGER__</td></tr>
<tr><th>止损 / 失效</th><td style="text-align:left">__BC_STOP__</td></tr>
<tr><th>观察点</th><td style="text-align:left">__BC_WATCH__</td></tr>
</tbody>
</table>
<div class="note"><b>边界：</b>__BC_DISCLAIMER__ 本报告不含样本外回测、跨标的验证与消息面检索，不得据此直接下单。</div>
</div>

<div class="card"><h2>六章技术分析实战课程</h2><p class="note">以下课程以本次 TQ 实际日线数据为案例；所有日期、价格、成交量和指标均由原始K线计算。周K/月K由日线聚合，样本不足处会明确说明。</p>__COURSE_CONTENT__</div>

<div class="disclaimer">
<b>免责声明</b>：以上内容基于公开数据和量化分析，仅供参考，不构成投资建议。市场有风险，投资需谨慎。任何投资决策应结合个人风险承受能力、资金状况和投资目标独立判断，必要时咨询持牌专业机构。过往表现不预示未来收益。
</div>
</div>

<script>
var CD = __CHART__;
function sw(id,el){
  document.getElementById('k').classList.add('hidden');
  document.getElementById('kt').classList.add('hidden');
  document.getElementById(id).classList.remove('hidden');
  var ts=document.querySelectorAll('.tab'); for(var i=0;i<ts.length;i++)ts[i].classList.remove('on');
  el.classList.add('on');
}
function svgNode(id,markup){document.getElementById(id).innerHTML='<svg viewBox="0 0 1000 320" role="img" aria-label="行情分析图" style="width:100%;height:100%;font-family:Arial,sans-serif">'+markup+'</svg>';}
function linePath(values,x0,y0,w,h,min,max){return values.map(function(v,i){var x=x0+i*w/Math.max(1,values.length-1),y=y0+h-(v-min)/(max-min||1)*h;return (i?'L':'M')+x.toFixed(1)+','+y.toFixed(1)}).join(' ');}
(function(){
 var n=CD.dates.length, vals=CD.ohlc.flatMap(function(x){return [x[2],x[3]]}),min=Math.min.apply(null,vals),max=Math.max.apply(null,vals),plotTop=18,plotH=185,baseY=220,step=900/Math.max(1,n);
 var s='<line x1="45" y1="220" x2="960" y2="220" stroke="#ccd3dc"/>';
 CD.ohlc.forEach(function(v,i){var x=50+i*step+step/2,up=v[1]>=v[0],col=up?'#d93025':'#0f9d58',yH=plotTop+(max-v[3])/(max-min||1)*plotH,yL=plotTop+(max-v[2])/(max-min||1)*plotH,yO=plotTop+(max-v[0])/(max-min||1)*plotH,yC=plotTop+(max-v[1])/(max-min||1)*plotH;s+='<line x1="'+x+'" y1="'+yH+'" x2="'+x+'" y2="'+yL+'" stroke="'+col+'"/><rect x="'+(x-step*.28)+'" y="'+Math.min(yO,yC)+'" width="'+Math.max(2,step*.56)+'" height="'+Math.max(1,Math.abs(yC-yO))+'" fill="'+col+'"/>';});
 s+='<text x="50" y="248" fill="#667085" font-size="12">'+CD.dates[0]+'</text><text x="900" y="248" fill="#667085" font-size="12">'+CD.dates[n-1]+'</text>';
 var vmax=Math.max.apply(null,CD.vols.concat([1]));
 CD.vols.forEach(function(v,i){var x=50+i*step+step/2,h=v/vmax*48;s+='<rect x="'+(x-step*.28)+'" y="'+(305-h)+'" width="'+Math.max(2,step*.56)+'" height="'+h+'" fill="#9aa7b8"/>';});
 svgNode('chart1',s);
 var vmax2=Math.max.apply(null,CD.vols.concat([1])),bars='';
 CD.vols.forEach(function(v,i){var x=50+i*step+step/2,h=v/vmax2*230;bars+='<rect x="'+(x-step*.3)+'" y="'+(270-h)+'" width="'+Math.max(2,step*.6)+'" height="'+h+'" fill="#9aa7b8"/>';});
 var avg=CD.vma10.filter(function(x){return x!==null}),vmin=Math.min.apply(null,avg.concat([0])),vmax3=Math.max.apply(null,avg.concat([1]));
 bars+='<path d="'+linePath(CD.vma10.map(function(v){return v===null?vmin:v}),50,25,900,230,vmin,vmax3)+'" fill="none" stroke="#d93025" stroke-width="3"/>';
 svgNode('chart2',bars);
 var total=CD.inside+CD.outside,ratio=total?CD.outside/total:0;
 var flow='<text x="70" y="80" font-size="18" fill="#344054">外盘（主动买入）</text><rect x="70" y="100" width="850" height="42" rx="6" fill="#e7ebf0"/><rect x="70" y="100" width="'+(850*ratio)+'" height="42" rx="6" fill="#d93025"/><text x="70" y="180" font-size="18" fill="#344054">内盘（主动卖出）</text><rect x="70" y="200" width="850" height="42" rx="6" fill="#e7ebf0"/><rect x="70" y="200" width="'+(850*(1-ratio))+'" height="42" rx="6" fill="#0f9d58"/><text x="70" y="285" font-size="16" fill="#667085">外盘占比 '+(ratio*100).toFixed(1)+'% · 内盘占比 '+((1-ratio)*100).toFixed(1)+'%</text>';
 svgNode('chart3',flow);
})();
</script>
<script>
document.querySelectorAll('.quiz-options button').forEach(function(b){
 b.addEventListener('click',function(){
  var out=b.parentNode.querySelector('.quiz-answer');
  out.textContent='答案：'+b.getAttribute('data-correct')+'。'+b.getAttribute('data-explain');
 });
});
</script>
</body>
</html>
"""


def sign(v):
    return "+" if v >= 0 else ""


def build(m, chart):
    s = m["snapshot"]
    vol = m["volume"]
    mf = m["moneyflow"]
    perf = m["performance"]
    name = m["name"] or m["code"]
    code = m["code"]
    asof = m["as_of"]

    title = f"{code} {name} · 量能与资金流分析"
    time_short = s.get("hqdate", asof.replace("-", ""))

    tldr = []
    tldr.append(
        f"<li><b>量能水位：</b>当日成交 {vol['today_yi']:.2f} 亿股（前一日 {vol['prev_yi']:.2f} 亿股），"
        f"量比（对 5 日均量）<b>{vol['vr5']:.2f}</b>、对 20 日均量 <b>{vol['vr20']:.2f}</b>；"
        f"60 日中位量 {vol['med60_yi']:.2f} 亿股。"
        + ("当日显著放量。" if vol["vr20"] > 1.5 else ("当日缩量。" if vol["vr20"] < 0.7 else "当日量能接近常态。"))
        + "</li>"
    )
    if m["top_volume_days"]:
        t = m["top_volume_days"][0]
        tldr.append(
            f"<li><b>近期峰量：</b>{t['date']} 成交 <b>{t['vol_yi']:.2f} 亿股</b>，"
            f"当日实体涨跌 {t['chg']:+.2f}%。放量方向需结合价格位置判断，宽基 ETF 的巨量常对应申赎/调样，未必等同方向性下注。</li>"
        )
    direction = "净流入" if mf["net_active_yi"] > 0 else "净流出"
    tldr.append(
        f"<li><b>资金流：</b>盘口外盘占比 <b>{mf['outside_ratio']*100:.1f}%</b>，"
        f"净主动买入约 <b>{abs(mf['net_active_yi']):.2f} 亿元</b>（{direction}）；"
        f"20 日 CMF = <b>{mf['cmf20']:+.3f}</b>，"
        + ("中期资金亦为净流入，方向一致。" if mf["cmf20"] > 0.05
           else ("中期资金仍为净流出，与当日盘口背离，单日信号不足以确认趋势反转。" if mf["cmf20"] < -0.05
                 else "中期资金基本中性。"))
        + "</li>"
    )
    tldr.append(
        f"<li><b>价格背景：</b>近 5 日 {sign(perf['chg5'])}{perf['chg5']:.2f}%｜近 20 日 {sign(perf['chg20'])}{perf['chg20']:.2f}%｜"
        f"近 60 日 {sign(perf['chg60'])}{perf['chg60']:.2f}%｜年初至今 {sign(perf['chg_ytd'])}{perf['chg_ytd']:.2f}%。"
        f"现价 {s['now']:.3f}，IOPV {s['iopv']:.3f}（溢价 {(s['now']/s['iopv']-1)*100:+.2f}%）。</li>"
    )

    def kpi(label, value, cls=""):
        return f'<div class="kpi"><div class="l">{label}</div><div class="v {cls}">{value}</div></div>'

    kpis = "".join([
        kpi("最新价", f"{s['now']:.3f}", "red" if s["now"] >= s["lastclose"] else "green"),
        kpi("涨跌幅", f"{(s['now']/s['lastclose']-1)*100:+.2f}%", "red" if s["now"] >= s["lastclose"] else "green"),
        kpi("成交额", f"{s['amount_wan']/1e4:.2f} 亿"),
        kpi("成交量", f"{s['volume_lots']/1e4:.1f} 万手"),
        kpi("换手率", f"{s['turnover']:.2f}%"),
        kpi("规模", f"{s['size_yi']:.2f} 亿"),
    ])

    snapnote = (
        f"现价 {s['now']:.3f}｜昨收 {s['lastclose']:.3f}｜今开 {s['open']:.3f}｜最高 {s['high']:.3f}｜"
        f"最低 {s['low']:.3f}｜均价 {s['avg']:.3f}｜IOPV {s['iopv']:.3f}｜委比 {s['weibi']:.2f}。"
        f"数据来源：通达信 TQ 快照，{time_short}。"
    )

    rows = []
    for d, o in zip(chart["dates"], chart["ohlc"]):
        cls = "red" if o[1] >= o[0] else "green"
        rows.append(f"<tr><td>{d}</td><td class='{cls}'>{o[1]:.3f}</td></tr>")

    volnote = (
        f"近 20 个完整交易日：上涨日均量 <b>{vol['upv_yi']:.2f} 亿股</b>，下跌日均量 <b>{vol['dnv_yi']:.2f} 亿股</b>，"
        f"比值 <b>{vol['updown_ratio']:.2f}</b>（>1 表示量能偏多）。60 日量能中位数 {vol['med60_yi']:.2f} 亿股。<br>"
        "对于宽基 ETF，巨额成交常含一级申赎与做市商对冲，单看放量判断方向容易误读，需结合 IOPV 溢价率与份额变化验证。"
    )
    flownNote = (
        f"盘口主动买卖：外盘（主动买入）{s['outside']/1e4:.2f} 万手，内盘（主动卖出）{s['inside']/1e4:.2f} 万手，"
        f"主动买入占比 <b>{mf['outside_ratio']*100:.1f}%</b>。<br>"
        f"20 日 CMF（蔡金资金流）= <b>{mf['cmf20']:+.3f}</b>；{'正值表示中期资金净流入，负值表示净流出' if mf['cmf20']>=0 else '负值表示中期资金整体净流出'}。<br>"
        "<b>口径提示：</b>内/外盘与 CMF 均为基于成交数据的统计推断，不等同于真实主力账户进出；ETF 申赎数据需基金公司公告确认，本报告未包含。"
    )

    bc = m.get("buycase") or {}
    if bc:
        dim_rows = []
        for d in bc.get("dimensions", []):
            state = d["state"]
            cls = ("st-ok" if state == "支持" else "st-no" if state == "不支持"
                   else "st-mid" if state in ("中性", "偏贵（贴近压力）", "合理", "观望")
                   else "st-na")
            dim_rows.append(
                f"<tr><td>{d['name']}</td><td><span class='st {cls}'>{state}</span></td>"
                f"<td style='text-align:left'>{d['basis']}</td></tr>"
            )
        vetoes = bc.get("gate_veto") or []
        gate_html = (
            '<div class="veto"><b>硬否决触发，买入依据不成立：</b>'
            + "；".join(vetoes) + "</div>"
        ) if vetoes else (
            '<div class="pass"><b>未触发硬否决</b>：趋势/资金未同时转空，量价无放量滞涨否决项。'
            '仍受证据等级上限约束，档位见上。</div>'
        )
        watch_html = "<br>".join("• " + w for w in bc["triplet"]["watchpoints"])
        bc_rep = {
            "__BC_TIER__": bc["tier"],
            "__BC_GRADE__": bc["evidence_grade"],
            "__BC_VETO_N__": str(len(vetoes)),
            "__BC_GATE__": gate_html,
            "__BC_ROWS__": "".join(dim_rows),
            "__BC_GRADE_BASIS__": bc["evidence_basis"],
            "__BC_TRIGGER__": bc["triplet"]["trigger"],
            "__BC_STOP__": bc["triplet"]["stop"],
            "__BC_WATCH__": watch_html,
            "__BC_DISCLAIMER__": bc["disclaimer"],
        }
    else:
        bc_rep = {k: "未评估（旧版数据文件，无买入依据字段）" for k in [
            "__BC_TIER__", "__BC_GRADE__", "__BC_VETO_N__", "__BC_GATE__", "__BC_ROWS__",
            "__BC_GRADE_BASIS__", "__BC_TRIGGER__", "__BC_STOP__", "__BC_WATCH__",
            "__BC_DISCLAIMER__"]}

    cmf20 = mf["cmf20"]
    cmf_desc = ("中期净流入" if cmf20 > 0.05 else ("中期净流出" if cmf20 < -0.05 else "中性"))
    vr_med60 = vol["today_yi"] / vol["med60_yi"] if vol["med60_yi"] else 0

    from course_content import build_course_html
    course_html = build_course_html(chart, m)

    rep = {
        "__COURSE_CONTENT__": course_html,
        "__TITLE__": title, "__TAG__": "盘中快照" if s.get("hqdate") else "盘后",
        "__ASOF__": asof, "__SNAPTIME__": "", "__NAME__": name, "__CODE__": code,
        "__TLDR__": "".join(tldr), "__KPIS__": kpis, "__SNAPNOTE__": snapnote,
        "__TABLE__": "".join(rows), "__VOLNOTE__": volnote, "__FLOWNOTE__": flownNote,
        "__CHART__": json.dumps(chart, ensure_ascii=False),
        # 量能解释卡
        "__TODAY_YI__": f"{vol['today_yi']:.2f}",
        "__PREV_YI__": f"{vol['prev_yi']:.2f}",
        "__V5_YI__": f"{vol['v5_yi']:.2f}",
        "__V20_YI__": f"{vol['v20_yi']:.2f}",
        "__VR5__": f"{vol['vr5']:.2f}",
        "__VR20__": f"{vol['vr20']:.2f}",
        "__MED60_YI__": f"{vol['med60_yi']:.2f}",
        "__VR_MED60__": f"{vr_med60:.1f}",
        "__UPV_YI__": f"{vol['upv_yi']:.2f}",
        "__DNV_YI__": f"{vol['dnv_yi']:.2f}",
        "__UPDOWN_RATIO__": f"{vol['updown_ratio']:.2f}",
        # 资金流解释卡
        "__INSIDE_WAN__": f"{s['inside']/1e4:.2f}",
        "__OUTSIDE_WAN__": f"{s['outside']/1e4:.2f}",
        "__OUTSIDE_RATIO__": f"{mf['outside_ratio']*100:.1f}",
        "__OUTSIDE__": f"{s['outside']-s['inside']:+,.0f}",
        "__INSIDE__": f"{s['inside']:,.0f}",
        "__VOL_LOTS__": f"{s['volume_lots']:,.0f}",
        "__AMOUNT__": f"{s['amount_wan']/1e4:.2f}",
        "__NET_ACTIVE_YI__": f"{mf['net_active_yi']:.2f}",
        "__CMF_MFV_SUM_E__": f"{mf.get('cmf20_mfv_sum', 0)/1e8:.4f}",
        "__CMF_VOL_SUM_E__": f"{mf.get('cmf20_vol_sum', 0)/1e8:.4f}",
        "__CMF20__": f"{cmf20:+.3f}",
        "__CMF_DESC__": cmf_desc,
    }
    rep.update(bc_rep)
    out = TPL
    for k, v in rep.items():
        out = out.replace(k, v)
    return out


def main():
    if len(sys.argv) < 4:
        print("Usage: python build_report.py <METRICS_JSON> <CHART_JSON> <OUTPUT_HTML>")
        sys.exit(2)
    m = json.load(open(sys.argv[1], encoding="utf-8"))
    c = json.load(open(sys.argv[2], encoding="utf-8"))
    html = build(m, c)
    with open(sys.argv[3], "w", encoding="utf-8") as f:
        f.write(html)
    print("REPORT_OK")
    print("OUT", sys.argv[3])


if __name__ == "__main__":
    main()
