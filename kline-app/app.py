#!/usr/bin/env python3
"""K线图 - 单文件版,无需任何第三方库,Python3直接运行"""
import json, re, urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote

HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>K线图</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#0f172a;color:#e2e8f0}
.bar{background:#1e293b;padding:10px 16px;display:flex;gap:8px;align-items:center;position:sticky;top:0;z-index:10}
.bar input{flex:1;padding:9px 12px;border:1px solid #334155;border-radius:8px;font-size:14px;background:#0f172a;color:#e2e8f0;outline:none}
.bar input:focus{border-color:#3b82f6}
.bar select{padding:9px 8px;border:1px solid #334155;border-radius:8px;font-size:13px;background:#0f172a;color:#e2e8f0}
.bar button{padding:9px 16px;border:none;border-radius:8px;background:#3b82f6;color:#fff;font-weight:600;cursor:pointer}
#results{position:absolute;top:52px;left:16px;right:16px;background:#1e293b;border-radius:8px;max-height:240px;overflow-y:auto;z-index:20;box-shadow:0 8px 24px rgba(0,0,0,.4);display:none}
#results .item{padding:8px 14px;cursor:pointer;border-bottom:1px solid #334155;font-size:13px}
#results .item:hover{background:#1e3a5f}
#info{padding:8px 16px;font-size:13px;color:#94a3b8;display:none}
#chart{width:100%;height:calc(100vh - 52px)}
.tip{padding:6px 16px;font-size:12px;color:#64748b}
</style>
</head>
<body>
<div class="bar">
  <input id="kw" placeholder="输入股票代码或名称,如 600519 / 茅台" autocomplete="off">
  <select id="scale">
    <option value="240">日线</option><option value="1200">周线</option><option value="7200">月线</option>
    <option value="60">60分</option><option value="30">30分</option><option value="15">15分</option><option value="5">5分</option>
  </select>
  <button id="btn">搜索</button>
</div>
<div id="results"></div>
<div id="info"></div>
<div id="chart"></div>
<div class="tip">数据来源:新浪财经 | 红涨绿跌 | 可缩放拖拽</div>
<script>
const $=s=>document.querySelector(s);
let chart=echarts.init($('#chart'));
window.addEventListener('resize',()=>chart.resize());
let curS=null,curN=null;
async function search(){
  const kw=$('#kw').value.trim();if(!kw)return;
  $('#results').style.display='block';$('#results').innerHTML='<div class="item">搜索中...</div>';
  try{const r=await fetch('/api/search?keyword='+encodeURIComponent(kw));const d=await r.json();
    if(!d.length){$('#results').innerHTML='<div class="item">无结果</div>';return;}
    $('#results').innerHTML=d.map(x=>'<div class="item" data-s="'+x.sina+'" data-n="'+x.name+'">'+x.code+' '+x.name+'</div>').join('');
  }catch(e){$('#results').innerHTML='<div class="item">错误:'+e.message+'</div>';}
}
async function loadK(s,n){
  curS=s;curN=n;$('#results').style.display='none';$('#info').style.display='block';
  $('#info').textContent=n+' 加载中...';const scale=$('#scale').value;
  try{const r=await fetch('/api/kline?symbol='+s+'&scale='+scale);const d=await r.json();
    if(!d||!d.length){$('#info').textContent='无数据';return;}render(d,n);
  }catch(e){$('#info').textContent='失败:'+e.message;}
}
function render(data,name){
  const closes=data.map(d=>parseFloat(d.close));
  const ma=n=>data.map((_,i)=>i>=n-1?(closes.slice(i-n+1,i+1).reduce((a,b)=>a+b,0)/n):null);
  $('#info').textContent=name+'  '+data.length+'根  最新:'+closes[closes.length-1]+'  '+data[0].day+' ~ '+data[data.length-1].day;
  chart.setOption({
    backgroundColor:'#0f172a',
    tooltip:{trigger:'axis',axisPointer:{type:'cross'},backgroundColor:'#1e293b',borderColor:'#334155',textStyle:{color:'#e2e8f0'}},
    legend:{data:['K线','MA5','MA10','MA20','MA60','成交量'],top:5,textStyle:{color:'#94a3b8'}},
    grid:[{left:60,right:30,top:40,height:'58%'},{left:60,right:30,top:'74%',height:'16%'}],
    xAxis:[
      {type:'category',data:data.map(d=>d.day),scale:true,boundaryGap:false,axisLine:{onZero:false,lineStyle:{color:'#334155'}},splitLine:{show:false},axisLabel:{fontSize:10,color:'#64748b'}},
      {type:'category',gridIndex:1,data:data.map(d=>d.day),axisLabel:{show:false}}
    ],
    yAxis:[
      {scale:true,splitArea:{show:true},axisLabel:{color:'#64748b'},splitLine:{lineStyle:{color:'#1e293b'}}},
      {gridIndex:1,splitNumber:2,axisLabel:{color:'#64748b'},splitLine:{lineStyle:{color:'#1e293b'}}}
    ],
    dataZoom:[
      {type:'inside',xAxisIndex:[0,1],start:60,end:100},
      {type:'slider',xAxisIndex:[0,1],start:60,end:100,height:18,bottom:8,dataBackground:{areaStyle:{color:'#334155'}},textStyle:{color:'#64748b'}}
    ],
    series:[
      {name:'K线',type:'candlestick',data:data.map(d=>[parseFloat(d.open),parseFloat(d.close),parseFloat(d.low),parseFloat(d.high)]),itemStyle:{color:'#dc2626',color0:'#16a34a',borderColor:'#dc2626',borderColor0:'#16a34a'}},
      {name:'MA5',type:'line',data:ma(5),smooth:true,symbol:'none',lineStyle:{width:1,color:'#f59e0b'}},
      {name:'MA10',type:'line',data:ma(10),smooth:true,symbol:'none',lineStyle:{width:1,color:'#8b5cf6'}},
      {name:'MA20',type:'line',data:ma(20),smooth:true,symbol:'none',lineStyle:{width:1,color:'#3b82f6'}},
      {name:'MA60',type:'line',data:ma(60),smooth:true,symbol:'none',lineStyle:{width:1,color:'#6b7280'}},
      {name:'成交量',type:'bar',xAxisIndex:1,yAxisIndex:1,data:data.map(d=>parseInt(d.volume)||0),itemStyle:{color:'#93c5fd'}}
    ]
  },true);
}
$('#btn').addEventListener('click',search);
$('#kw').addEventListener('keydown',e=>{if(e.key==='Enter')search();});
$('#results').addEventListener('click',e=>{const i=e.target.closest('.item');if(i&&i.dataset.s)loadK(i.dataset.s,i.dataset.n);});
$('#scale').addEventListener('change',()=>{if(curS)loadK(curS,curN);});
document.addEventListener('click',e=>{if(!e.target.closest('.bar')&&!e.target.closest('#results'))$('#results').style.display='none';});
</script>
</body>
</html>'''


def fetch(url, encoding="utf-8"):
    req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode(encoding, errors="replace")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/api/search":
            kw = qs.get("keyword", [""])[0]
            try:
                text = fetch(f"https://suggest3.sinajs.cn/suggest/type=11,12,13,14,15&key={quote(kw)}&name=suggestdata", encoding="gbk")
                m = re.search(r'"([^"]*)"', text)
                results = []
                if m and m.group(1).strip():
                    for item in m.group(1).split(";"):
                        if not item.strip():
                            continue
                        p = item.split(",")
                        if len(p) >= 5:
                            results.append({"code": p[2].strip(), "name": p[4].strip() or p[0].strip(), "sina": p[3].strip()})
                self._json(results[:20])
            except Exception as e:
                self._json({"error": str(e)}, 500)

        elif parsed.path == "/api/kline":
            symbol = qs.get("symbol", [""])[0]
            scale = qs.get("scale", ["240"])[0]
            datalen = qs.get("datalen", ["500"])[0]
            try:
                text = fetch(f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale={scale}&ma=no&datalen={datalen}")
                data = json.loads(text) if text else []
                self._json(data)
            except Exception as e:
                self._json({"error": str(e)}, 500)

        else:
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = 9000
    print(f"K线图服务启动: http://localhost:{port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
