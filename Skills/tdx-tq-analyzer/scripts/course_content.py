# -*- coding: utf-8 -*-
"""Six-chapter, real-market-data teaching content embedded in the stock report."""
import html
import math
from collections import defaultdict


def esc(x):
    return html.escape(str(x), quote=True)


def f(x, n=3):
    return "—" if x is None else f"{x:.{n}f}"


def _period_bars(dates, ohlc, vols, mode):
    buckets = {}
    for d, bar, vol in zip(dates, ohlc, vols):
        key = d[:7] if mode == "month" else d[:4] + "-W" + __import__("datetime").date.fromisoformat(d).strftime("%W")
        if key not in buckets:
            buckets[key] = [d, d, bar[0], bar[1], bar[2], bar[3], vol]
        else:
            b = buckets[key]
            b[1], b[3], b[4], b[5], b[6] = d, bar[1], min(b[4], bar[2]), max(b[5], bar[3]), b[6] + vol
    return list(buckets.items())


def _indicators(ohlc):
    closes = [x[1] for x in ohlc]
    highs = [x[3] for x in ohlc]
    lows = [x[2] for x in ohlc]
    def ema(values, period):
        out, alpha = [], 2 / (period + 1)
        for i, v in enumerate(values):
            out.append(v if i == 0 else alpha * v + (1-alpha) * out[-1])
        return out
    dif = [a-b for a,b in zip(ema(closes,12),ema(closes,26))]
    dea = ema(dif,9)
    hist = [(a-b)*2 for a,b in zip(dif,dea)]
    changes = [closes[i]-closes[i-1] for i in range(1,len(closes))]
    gains = [max(x,0) for x in changes[-14:]]
    losses = [max(-x,0) for x in changes[-14:]]
    rsi = 100 if sum(losses)==0 else 100-100/(1+(sum(gains)/max(1e-12,sum(losses))))
    window = closes[-20:]
    mean = sum(window)/len(window) if window else None
    sd = math.sqrt(sum((x-mean)**2 for x in window)/len(window)) if window else None
    tr=[]
    for i in range(1,len(ohlc)):
        tr.append(max(highs[i]-lows[i],abs(highs[i]-closes[i-1]),abs(lows[i]-closes[i-1])))
    atr=sum(tr[-14:])/len(tr[-14:]) if tr else None
    return {"dif":dif[-1],"dea":dea[-1],"macd":hist[-1],"rsi14":rsi,
            "bb_mid":mean,"bb_up":mean+2*sd if mean is not None else None,
            "bb_low":mean-2*sd if mean is not None else None,"atr14":atr}



def _svg_wrap(title, body, height=250):
    return (f'<div class="course-diagram"><div class="diagram-title">{esc(title)}</div>'
            f'<svg viewBox="0 0 960 {height}" role="img" aria-label="{esc(title)}" '
            f'preserveAspectRatio="xMidYMid meet">{body}</svg></div>')


def _candle_svg(bars, dates, indices, width=900, height=270, labels=True):
    if not indices:
        return _svg_wrap("无可绘制K线", "", height)
    subset=[(i,bars[i]) for i in indices]
    lo=min(b[2] for _,b in subset); hi=max(b[3] for _,b in subset)
    pad=max((hi-lo)*.12,0.001); lo-=pad; hi+=pad
    left,right,top,bottom=58,width-18,18,height-45
    xstep=(right-left)/max(len(subset),1)
    y=lambda v: bottom-(v-lo)/(hi-lo)*(bottom-top)
    out=[f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#98a2b3"/>',
         f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#98a2b3"/>']
    for tick in range(5):
        v=lo+(hi-lo)*tick/4; yy=y(v)
        out.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{right}" y2="{yy:.1f}" stroke="#edf0f3"/>')
        out.append(f'<text x="5" y="{yy+4:.1f}" font-size="12" fill="#667085">{v:.3f}</text>')
    for j,(i,b) in enumerate(subset):
        o,c,l,h=b; x=left+(j+.5)*xstep; color="#d93025" if c>=o else "#159455"
        out.append(f'<line x1="{x:.1f}" y1="{y(h):.1f}" x2="{x:.1f}" y2="{y(l):.1f}" stroke="{color}" stroke-width="2"/>')
        yt=min(y(o),y(c)); bh=max(abs(y(o)-y(c)),2)
        out.append(f'<rect x="{x-xstep*.27:.1f}" y="{yt:.1f}" width="{max(xstep*.54,2):.1f}" height="{bh:.1f}" fill="{color}" stroke="{color}"/>')
        if labels and (j%max(1,len(subset)//6)==0 or j==len(subset)-1):
            out.append(f'<text x="{x:.1f}" y="{bottom+18}" text-anchor="middle" font-size="11" fill="#667085">{esc(dates[i][-5:])}</text>')
    return _svg_wrap("真实K线图", "".join(out), height)


def _single_candle_svg(bar, date):
    o,c,l,h=bar; top=28; bottom=220; mid=460
    lo=min(l,o,c)-max((h-l)*.35,.004); hi=max(h,o,c)+max((h-l)*.35,.004)
    y=lambda v: bottom-(v-lo)/(hi-lo)*(bottom-top)
    color="#d93025" if c>=o else "#159455"
    bodytop=min(y(o),y(c)); bodyh=max(abs(y(o)-y(c)),3)
    parts=[f'<line x1="{mid}" y1="{y(h):.1f}" x2="{mid}" y2="{y(l):.1f}" stroke="{color}" stroke-width="5"/>',
           f'<rect x="410" y="{bodytop:.1f}" width="100" height="{bodyh:.1f}" fill="{color}" rx="2"/>']
    # price labels and leader lines, aligned to the four actual price levels
    labels=[("最高 H",h,70,"#344054"),("收盘 C",c,330,"#d93025" if c>=o else "#159455"),
            ("开盘 O",o,590,"#344054"),("最低 L",l,850,"#344054")]
    for label,v,x,col in labels:
        yy=y(v)
        parts.append(f'<line x1="515" y1="{yy:.1f}" x2="{x-12}" y2="{yy:.1f}" stroke="{col}" stroke-dasharray="4 3"/>')
        parts.append(f'<text x="{x}" y="{yy-7:.1f}" font-size="16" fill="{col}" text-anchor="middle">{label} {v:.3f}</text>')
    parts += [f'<text x="460" y="250" text-anchor="middle" font-size="14" fill="#667085">{esc(date)} · {("阳线" if c>o else "阴线" if c<o else "平盘")}</text>',
              f'<text x="460" y="18" text-anchor="middle" font-size="13" fill="#667085">上影线 {h-max(o,c):.3f}　实体 {abs(c-o):.3f}　下影线 {min(o,c)-l:.3f}</text>']
    return _svg_wrap("今日真实日K：四价、实体与影线逐项标注", "".join(parts), 270)


def _volume_svg(vols, dates, n=25):
    start=max(0,len(vols)-n); data=vols[start:]; ds=dates[start:]
    if not data: return _svg_wrap("成交量", "")
    mx=max(data)*1.2 or 1; left,right,top,bottom=55,920,20,210
    step=(right-left)/len(data); out=[]
    for j,v in enumerate(data):
        x=left+(j+.5)*step; y=bottom-v/mx*(bottom-top)
        out.append(f'<rect x="{x-step*.3:.1f}" y="{y:.1f}" width="{step*.6:.1f}" height="{bottom-y:.1f}" fill="#7da6d8"/>')
        if j%5==0 or j==len(data)-1: out.append(f'<text x="{x:.1f}" y="232" text-anchor="middle" font-size="11" fill="#667085">{esc(ds[j][-5:])}</text>')
    for p,col in [(5,"#d97706"),(20,"#159455")]:
        ma=[sum(data[max(0,i-p+1):i+1])/len(data[max(0,i-p+1):i+1]) for i in range(len(data))]
        pts=" ".join(f"{left+(i+.5)*step:.1f},{bottom-v/mx*(bottom-top):.1f}" for i,v in enumerate(ma))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2"/>')
    out.append('<text x="60" y="14" font-size="12" fill="#667085">蓝柱：真实成交量　橙线：5日均量　绿线：20日均量</text>')
    return _svg_wrap("最近交易日成交量柱与均量线", "".join(out), 250)


def _line_svg(values, dates, title, color="#3267a8", n=60, zero=False):
    start=max(0,len(values)-n); vals=values[start:]; ds=dates[start:]
    if not vals:return _svg_wrap(title,"")
    lo=min(vals); hi=max(vals)
    if zero: lo=min(lo,0);hi=max(hi,0)
    if hi==lo: hi+=1
    left,right,top,bottom=55,920,20,205
    x=lambda i:left+(right-left)*i/max(len(vals)-1,1)
    y=lambda v:bottom-(v-lo)/(hi-lo)*(bottom-top)
    out=[]
    for t in range(5):
        v=lo+(hi-lo)*t/4; yy=y(v)
        out.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{right}" y2="{yy:.1f}" stroke="#edf0f3"/>')
        out.append(f'<text x="4" y="{yy+4:.1f}" font-size="11" fill="#667085">{v:.3f}</text>')
    pts=" ".join(f"{x(i):.1f},{y(v):.1f}" for i,v in enumerate(vals))
    out.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5"/>')
    out.append(f'<circle cx="{x(len(vals)-1):.1f}" cy="{y(vals[-1]):.1f}" r="4" fill="{color}"/>')
    out.append(f'<text x="{right}" y="238" text-anchor="end" font-size="12" fill="#667085">最新 {esc(ds[-1])}：{vals[-1]:.4f}</text>')
    return _svg_wrap(title,"".join(out),250)


def _price_ma_svg(bars, dates, n=60):
    start=max(0,len(bars)-n); closes=[b[1] for b in bars]
    price=_candle_svg(bars,dates,list(range(start,len(bars))),height=280)
    # add moving average lines as a separate synchronized panel for readability
    out=[]
    for p,col in [(5,"#d97706"),(20,"#159455"),(60,"#805ad5")]:
        vals=[None if i<p-1 else sum(closes[i-p+1:i+1])/p for i in range(start,len(closes))]
        valid=[(j,v) for j,v in enumerate(vals) if v is not None]
        if valid: out.append(f'<text x="20" y="{20+len(out)*19}" font-size="12" fill="{col}">MA{p} 最新 {valid[-1][1]:.3f}</text>')
    return price + _svg_wrap("均线读图提示", "".join(out), 65)


def _period_svg(rows, title):
    if not rows:return _svg_wrap(title,"")
    # Render OHLC period bars as candles, with real aggregated dates/values.
    bars=[]; dates=[]
    for key,b in rows:
        dates.append(b[1])
        bars.append([b[2],b[3],b[4],b[5]])
    return _candle_svg(bars,dates,list(range(len(bars))),height=250)


def _macd_series(closes):
    def ema(vals,p):
        a=2/(p+1); out=[]
        for i,v in enumerate(vals): out.append(v if i==0 else a*v+(1-a)*out[-1])
        return out
    fast,slow=ema(closes,12),ema(closes,26)
    dif=[x-y for x,y in zip(fast,slow)]; dea=ema(dif,9)
    return dif,dea,[(x-y)*2 for x,y in zip(dif,dea)]


def _section(num, title, goal, concept, formula, case, steps, caution, question, answer, explanation, diagram=""):
    return f"""
<section class="course-chapter">
 <h3>第{num}章　{esc(title)}</h3>
 <p class="course-goal"><b>本章目标：</b>{goal}</p>
 {diagram}<div class="course-grid">
  <div><h4>一、原理与概念</h4><p>{concept}</p><div class="course-formula">{formula}</div></div>
  <div><h4>二、510330真实行情案例</h4><p>{case}</p></div>
 </div>
 <h4>三、跟着数据做分析</h4><ol>{''.join('<li>'+x+'</li>' for x in steps)}</ol>
 <p class="course-caution"><b>容易误判：</b>{caution}</p>
 <div class="course-quiz"><b>四、本章练习：</b>{question}
  <div class="quiz-options"><button type="button" data-correct="{answer}" data-explain="{esc(explanation)}">查看答案与解析</button><span class="quiz-answer"></span></div>
 </div>
</section>"""


def build_course_html(chart, metrics):
    dates = chart.get("full_dates") or []
    bars = chart.get("full_ohlc") or []
    vols = chart.get("full_vols") or []
    if not dates or len(dates) != len(bars) or len(bars) != len(vols):
        dates, bars, vols = [], [], []
    latest_date = dates[-1] if dates else metrics.get("as_of", "未知")
    if not bars:
        return '<p class="course-caution">没有可用的真实日线数组，六章教学案例暂不能生成。请先重新运行 TQ 数据采集；本报告不会用示例数字冒充行情。</p>'
    last = bars[-1]
    op, close, low, high = last
    body = abs(close-op)
    upper = high-max(op,close)
    lower = min(op,close)-low
    direction = "阳线" if close > op else ("阴线" if close < op else "平盘线")
    body_pct = body/op*100 if op else 0
    v_last = vols[-1]
    v_prev = vols[-2] if len(vols)>1 else None
    vma5 = sum(vols[-5:])/len(vols[-5:])
    vma20 = sum(vols[-20:])/len(vols[-20:])
    vr5 = v_last/vma5 if vma5 else 0
    vr20 = v_last/vma20 if vma20 else 0
    closes = [x[1] for x in bars]
    ma5 = sum(closes[-5:])/min(5,len(closes))
    ma20 = sum(closes[-20:])/min(20,len(closes))
    ma60 = sum(closes[-60:])/min(60,len(closes))
    ind = _indicators(bars)
    wk = _period_bars(dates,bars,vols,"week")
    mo = _period_bars(dates,bars,vols,"month")
    def period_desc(rows, name):
        if len(rows)<2:
            return f"当前可聚合出 {len(rows)} 根{name}，样本不足以判断长期结构。"
        a,b=rows[-2][1],rows[-1][1]
        return (f"共聚合 {len(rows)} 根{name}；最近一根覆盖 {b[0]} 至 {b[1]}，"
                f"开盘 {b[2]:.3f}、收盘 {b[3]:.3f}、最低 {b[4]:.3f}、最高 {b[5]:.3f}，"
                f"成交量 {b[6]:.3f} 亿股；前一根收盘 {a[3]:.3f}。")
    weekly=period_desc(wk,"周K")
    monthly=period_desc(mo,"月K")
    trend = "收盘高于MA5与MA20" if close>ma5 and close>ma20 else ("收盘低于MA5与MA20" if close<ma5 and close<ma20 else "收盘处于MA5与MA20之间")
    candle_case=(f"{latest_date}：开盘 {op:.3f}、收盘 {close:.3f}、最高 {high:.3f}、最低 {low:.3f}，"
                 f"为{direction}；实体 {body:.3f}（约占开盘价 {body_pct:.2f}%），"
                 f"上影 {upper:.3f}、下影 {lower:.3f}。")
    volume_case=(f"{latest_date} 成交 {v_last:.3f} 亿股；近5日均量 {vma5:.3f} 亿股，"
                 f"量比(5日) {vr5:.2f}；近20日均量 {vma20:.3f} 亿股，量比(20日) {vr20:.2f}。")
    trend_case=(f"最新收盘 {close:.3f}；MA5={ma5:.3f}、MA20={ma20:.3f}、MA60={ma60:.3f}。"
                f"按收盘与短中期均线的相对位置，当前属于“{trend}”。")
    indicator_case=(f"截至 {latest_date}，按日收盘价计算 RSI(14)={ind['rsi14']:.1f}；"
                    f"MACD DIF={ind['dif']:.4f}、DEA={ind['dea']:.4f}、柱体={ind['macd']:.4f}；"
                    f"BOLL(20,2) 中轨={f(ind['bb_mid'])}、上轨={f(ind['bb_up'])}、下轨={f(ind['bb_low'])}；"
                    f"ATR(14)={f(ind['atr14'])}。")
    multi_case=f"日线最近一根：{candle_case} {weekly} {monthly}"
    synthesis=(f"把证据放在一起：价格位置为“{trend}”；{volume_case} "
               f"CMF(20)={metrics.get('moneyflow',{}).get('cmf20',0):+.3f}（量价统计指标，并非真实账户资金流）。"
               "当前报告的原始日线样本为实际采集窗口，不代表完整牛熊周期。")
    sections=[]
    live_note = ("如果本次采集发生在交易时段，最新日K/当周K/当月K尚未完成；"
                 "盘中形态不能当作收盘确认。若在收盘后采集，则以TQ返回的最新完整日线为准。")
    sections.append('<p class="course-caution"><b>数据时点：</b>' + esc(live_note) +
                    ' 本次原始日线共 ' + str(len(bars)) + ' 根，覆盖 ' +
                    esc(dates[0]) + ' 至 ' + esc(dates[-1]) + '。</p>')
    sections.append(_section(1,"K线基础","能从开、高、低、收四价读出实体、影线和当日价格行为。",
      "一根K线记录一个时间周期内的四个价格。实体表示开盘与收盘之间的距离；上影线表示最高价到实体上沿，下影线表示实体下沿到最低价。先读事实，再解释多空。",
      "实体长度=|收盘价−开盘价|；上影=最高价−max(开盘价,收盘价)；下影=min(开盘价,收盘价)−最低价。",
      candle_case,
      ["先确认本报告周期是日K，不把盘中快照误当成完整收盘K线。","比较开盘与收盘，判断阳线、阴线或平盘。","比较实体与上下影线，描述冲高回落或探低回升的痕迹。","把这根K线放回前后交易日，不凭单根形态预测反转。"],
      "长下影只说明该周期内价格曾下探后收回；没有趋势位置和后续确认，不能直接称为买点。",
      "实体由哪两个价格决定？","A","开盘价与收盘价决定实体；最高价和最低价决定影线范围。", _single_candle_svg(last, latest_date)))
    sections.append(_section(2,"成交量","理解成交股数、均量与量比，辨别相对放量和缩量。",
      "成交量是一定周期内成交的证券数量；成交额是成交金额。放量/缩量必须相对一个明确基准来定义，均量线可平滑短期噪声。",
      "N日均量=最近N日成交量之和÷N；量比(N)=当日成交量÷前N日平均成交量（此处教学口径使用滚动均量）。",
      volume_case,
      ["先看量柱绝对值，再与5日、20日均量比较。","量比大于1表示高于所选均量基准，小于1表示低于基准。","把量能与同日K线方向一起读：放量上涨、放量下跌、缩量上涨各有不同含义。","宽基ETF还要考虑申赎、做市和指数调整等成交来源。"],
      "量比不是资金净流入指标；成交量放大也不等于机构看多。",
      "若当日成交量是20日均量的0.7倍，最准确的描述是什么？","B","当日成交量低于20日均量，属于相对缩量；不能单凭这一点判断涨跌方向。", _volume_svg(vols, dates)))
    sections.append(_section(3,"趋势分析","用高低点结构和均线判断趋势背景，并写出假设失效条件。",
      "上升结构通常表现为高点、低点逐步抬高；下降结构则表现为高点、低点逐步降低。移动平均线是过去收盘价的平滑值，具有滞后性。",
      "MA(N)=最近N个交易日收盘价之和÷N。均线描述过去，不预测未来。",
      trend_case,
      ["先观察近阶段高点和低点是否逐步抬高或降低。","再比较收盘价与MA5、MA20、MA60的位置。","均线多头/空头排列只能作为辅助证据，要与价格结构交叉验证。","写明趋势判断失效条件，例如有效跌破最近一个结构低点。"],
      "均线交叉是滞后信号；横盘时频繁交叉容易产生假信号。",
      "MA20的本质是什么？","C","MA20是最近20个交易日收盘价的算术平均，反映过去一段价格的平滑水平。", _price_ma_svg(bars, dates)))
    sections.append(_section(4,"日K/周K/月K多周期分析","学会用月线看大背景、周线看中期结构、日线看执行细节。",
      "周K/月K不是另一套独立行情，而是由日K聚合：开盘取周期首日开盘，收盘取周期末日收盘，最高取周期内最高，最低取周期内最低，成交量求和。",
      "周期聚合：O=首日O，C=末日C，H=max(H)，L=min(L)，V=Σ日成交量。",
      multi_case,
      ["先看月K的长期位置，但本次采集窗口可能只覆盖少数月份。","再看周K的中期方向，检查周收盘与周内高低点。","最后回到日K寻找具体价格行为与量能变化。","若日线与周线冲突，降低结论强度，不强行解释成同向。"],
      "本报告周/月K由采集到的日线聚合；窗口外历史没有被补齐，月线根数少时不能据此判断长期牛熊。",
      "周K的收盘价应取哪一天的收盘？","A","取该周最后一个实际交易日的收盘价；节假日不会虚构交易日。", _period_svg(wk, "周K") + _period_svg(mo, "月K")))
    sections.append(_section(5,"技术指标","理解常见指标的计算来源、读法与滞后性。",
      "指标是价格/成交量的二次加工，不是独立于行情的神秘信号。RSI衡量近期涨跌幅相对强弱；MACD比较快慢EMA；BOLL描述均值与波动区间；ATR衡量波动幅度。",
      "RSI=100−100/(1+平均上涨幅度÷平均下跌幅度)；DIF=EMA12−EMA26；DEA=EMA9(DIF)；BOLL=MA20±2σ。",
      indicator_case,
      ["先确认指标参数与计算口径，避免不同软件参数不一致。","RSI高低只描述强弱，不意味着立即反转。","MACD观察DIF/DEA相对位置、零轴和柱体变化。","BOLL看价格相对通道的位置；ATR只衡量波动，不判断方向。"],
      "指标由历史数据计算，存在滞后；多个同源指标同时发出信号，不代表证据完全独立。",
      "ATR(14)主要回答什么问题？","B","ATR衡量近期真实波幅/波动程度，不提供上涨或下跌方向。", _line_svg(ind["rsi14_series"], dates, "RSI(14)指标走势") if "rsi14_series" in ind else _line_svg([ind["rsi14"]]*len(dates), dates, "RSI(14)当前值") + _line_svg(_macd_series(closes)[0], dates, "MACD DIF走势", zero=True) + _line_svg(_macd_series(closes)[2], dates, "MACD柱体", color="#d97706", zero=True)))
    sections.append(_section(6,"量价关系综合应用","把趋势、周期、K线、成交量和指标组成可复核、可证伪的研究判断。",
      "综合分析不是把指标投票相加，而是先确定周期背景，再陈述价格事实、量能事实和指标状态，最后列出支持证据、反例与失效条件。",
      "分析顺序：周期背景 → 趋势结构 → 关键价位 → 量价确认 → 指标辅助 → 触发/失效条件。",
      synthesis,
      ["先用周/月周期确定背景，并注明样本长度限制。","在日线上描述价格与均线、前高前低的位置。","检查成交量相对均量是否放大，以及放量发生在上涨还是下跌日。","用CMF/RSI/MACD等辅助验证，不把指标当成资金账户事实。","写出反面证据和下一步观察条件；条件未满足前保持结论开放。"],
      "CMF、内外盘是成交数据推断，不等同基金申赎或真实主力账户流向；技术分析也不能替代估值、公告与风险评估。",
      "一个完整的量价结论至少应包含什么？","C","至少包括明确周期、价格事实、量能基准、解释、反例/风险以及结论失效条件。", _candle_svg(bars, dates, list(range(max(0,len(bars)-30),len(bars)))) + _volume_svg(vols, dates, 30)))
    return "\n".join(sections)
