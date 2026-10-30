import os, sys, json, subprocess, time

chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
output_file = "stock_data.json"

# 提取JSON from DOM: <pre>...</pre>
def extract_json_from_html(html):
    for tag in ["<pre>", "<pre ", "<xmp>", "<plaintext>"]:
        start = html.find(tag)
        if start >= 0:
            end = html.find("</", start + len(tag))
            if end >= 0:
                content = html[start + len(tag):end]
                # Strip HTML tags from the content
                while "<" in content and ">" in content:
                    a, b = content.find("<"), content.find(">", content.find("<"))
                    if a >= 0 and b >= 0:
                        content = content[:a] + content[b+1:]
                    else:
                        break
                return content.strip()
    return html.strip()

print("关闭 Chrome...", flush=True)
subprocess.run(["taskkill", "/f", "/im", "chrome.exe"], capture_output=True, timeout=10)
time.sleep(3)

all_data = {"data": {"diff": [], "total": 0}}
max_pages = 3

for page in range(1, max_pages + 1):
    url = ("https://82.push2.eastmoney.com/api/qt/clist/get?"
           f"pn={page}&pz=100&po=1&np=1"
           "&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3"
           "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
           "&fields=f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21")
    
    print(f"获取第 {page} 页...", flush=True)
    result = subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--dump-dom",
         "--no-first-run", "--no-default-browser-check",
         "--virtual-time-budget=15000", url],
        capture_output=True, timeout=30)
    
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    
    if result.returncode != 0:
        print(f"  返回码: {result.returncode}", flush=True)
        print(f"  stderr: {stderr[:200]}", flush=True)
    
    json_text = extract_json_from_html(stdout)
    
    try:
        data = json.loads(json_text)
        diff = data.get("data", {}).get("diff", [])
        total = data.get("data", {}).get("total", 0)
        all_data["data"]["diff"].extend(diff)
        all_data["data"]["total"] = total
        print(f"  获取到 {len(diff)} 只 (共{total})", flush=True)
        if page * 100 >= total:
            break
    except json.JSONDecodeError as e:
        print(f"  JSON解析失败: {e}", flush=True)
        print(f"  输出前200字符: {json_text[:200]}", flush=True)
    
    time.sleep(0.5)

if all_data["data"]["diff"]:
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False)
    print(f"成功! {len(all_data['data']['diff'])} 只股票已保存到 {output_file}", flush=True)
else:
    print("未获取到任何数据!", flush=True)
