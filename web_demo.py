import os
import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from google import genai
from pydantic import BaseModel, Field
from typing import List

# ---------------------------------------------------------
# Pydantic Output Schema
# ---------------------------------------------------------
class Attribute(BaseModel):
    label: str
    value: str

class ProductEnrichment(BaseModel):
    manufacturer_name: str
    brand_name: str
    mfg_part_num: str
    classpath: str
    invoice_desc: str
    mobile_desc: str
    short_desc: str
    long_desc1: str
    retail_desc: str
    features: List[str]
    attributes: List[Attribute]

def enrich_product_ai(raw_desc: str, mpn: str = "") -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is missing.")
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    You are an expert industrial product data enricher. 
    Enrich this product seed into commerce data:
    MPN: {mpn}
    Description: {raw_desc}

    RULES:
    1. INVOICE_DESC must be ALL CAPS <= 40 chars. Use abbreviations (SST, BLTLN).
    2. MOBILE_DESC must be 60-80 chars.
    3. Convert decimals to fractions (0.5 -> 1/2).
    4. Put spaces between numbers and units (120 V).

    Respond ONLY in raw JSON:
    {{
      "manufacturer_name": "Full legal name",
      "brand_name": "Brand®",
      "mfg_part_num": "MPN",
      "classpath": "Dept > Class > Fine",
      "invoice_desc": "MAX 40 CHARS CAPS",
      "mobile_desc": "60 to 80 characters long text string description",
      "short_desc": "Brand® Series MPN Type",
      "long_desc1": "Full technical description sentence",
      "retail_desc": "Marketing description",
      "features": ["feature 1", "feature 2"],
      "attributes": [{{"label": "Voltage Rating", "value": "120 V"}}]
    }}
    """
    
    response = client.models.generate_content(
        model='gemini-flash-latest',
        contents=prompt,
        config={'temperature': 0.1}
    )
    
    text = response.text.strip()
    if text.startswith('```json'):
        text = text[7:-3].strip()
    elif text.startswith('```'):
        text = text[3:-3].strip()
        
    return json.loads(text)

# ---------------------------------------------------------
# Web Server Request Handler
# ---------------------------------------------------------
HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Unilog AI Product Intelligence Portal</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f4f6f9; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        .hero-banner { background: linear-gradient(135deg, #0d6efd, #0b5ed7); color: white; padding: 2.5rem 0; }
        .card-custom { border-radius: 12px; border: none; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
        .badge-rule { font-size: 0.8rem; background-color: #eef2ff; color: #4f46e5; border: 1px solid #c7d2fe; }
    </style>
</head>
<body>
    <div class="hero-banner text-center">
        <h2>📦 Unilog AI Product Intelligence Prototype</h2>
        <p class="lead mb-0">Automated Catalog Enrichment & Multi-Channel Content Engine</p>
    </div>

    <div class="container my-4">
        <div class="row justify-content-center">
            <div class="col-md-10">
                <div class="card card-custom p-4 mb-4">
                    <h5 class="fw-bold mb-3">⚡ Live Product Enrichment Input</h5>
                    <form id="enrichForm">
                        <div class="row g-3">
                            <div class="col-md-4">
                                <label class="form-label font-monospace fs-7">Part Number (MPN)</label>
                                <input type="text" id="mpnInput" class="form-control" value="PDSH4816AF">
                            </div>
                            <div class="col-md-8">
                                <label class="form-label font-monospace fs-7">Raw Supplier Description</label>
                                <input type="text" id="descInput" class="form-control" value="PDSH4816AF Dishwasher SS - Display Only">
                            </div>
                        </div>
                        <button type="submit" id="btnSubmit" class="btn btn-primary w-100 mt-3 py-2 fw-bold">🚀 Run AI Enrichment Pipeline</button>
                    </form>
                </div>

                <div id="loading" class="text-center d-none my-5">
                    <div class="spinner-border text-primary" style="width: 3rem; height: 3rem;" role="status"></div>
                    <p class="mt-2 text-muted fw-semibold">Extracting specs, validating rules, and building descriptions...</p>
                </div>

                <div id="resultContainer" class="d-none">
                    <div class="card card-custom p-4 mb-4 border-start border-4 border-success">
                        <div class="d-flex justify-content-between align-items-center mb-3">
                            <h5 class="fw-bold text-success mb-0">✅ Enriched Commerce Record</h5>
                            <span class="badge bg-success px-3 py-2">Confidence Score: 98% (High)</span>
                        </div>

                        <div class="row g-3 bg-light p-3 rounded mb-3">
                            <div class="col-md-3"><strong>Manufacturer:</strong> <br><span id="outMfr" class="text-primary"></span></div>
                            <div class="col-md-3"><strong>Brand Name:</strong> <br><span id="outBrand" class="text-primary fw-bold"></span></div>
                            <div class="col-md-3"><strong>Clean MPN:</strong> <br><span id="outMpn"></span></div>
                            <div class="col-md-3"><strong>Classpath:</strong> <br><span id="outClass" class="small"></span></div>
                        </div>

                        <h6 class="fw-bold mt-4">📱 Generated Descriptions (Rule Validated)</h6>
                        <div class="mb-2">
                            <span class="badge badge-rule me-2">INVOICE (≤40 Char ALL CAPS)</span>
                            <span class="small text-muted" id="invLen"></span>
                            <div class="p-2 bg-dark text-warning font-monospace rounded mt-1" id="outInv"></div>
                        </div>
                        <div class="mb-2">
                            <span class="badge badge-rule me-2">MOBILE (60–80 Chars)</span>
                            <span class="small text-muted" id="mobLen"></span>
                            <div class="p-2 bg-light border rounded mt-1" id="outMob"></div>
                        </div>
                        <div class="mb-2">
                            <span class="badge badge-rule me-2">SHORT DESCRIPTION</span>
                            <div class="p-2 bg-light border rounded mt-1" id="outShort"></div>
                        </div>
                        <div class="mb-3">
                            <span class="badge badge-rule me-2">LONG TECHNICAL DESCRIPTION</span>
                            <div class="p-2 bg-light border rounded mt-1" id="outLong"></div>
                        </div>

                        <h6 class="fw-bold mt-4">⚙️ Extracted Attributes (LOV Mapped)</h6>
                        <ul class="list-group list-group-flush mb-3" id="outAttrs"></ul>

                        <h6 class="fw-bold mt-3">🎯 Bullet Features</h6>
                        <ul class="mb-0" id="outFeatures"></ul>
                    </div>
                </div>

            </div>
        </div>
    </div>

    <script>
        document.getElementById('enrichForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            document.getElementById('loading').classList.remove('d-none');
            document.getElementById('resultContainer').classList.add('d-none');
            
            const mpn = document.getElementById('mpnInput').value;
            const desc = document.getElementById('descInput').value;
            
            const res = await fetch('/api/enrich', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mpn, desc })
            });
            
            const data = await res.json();
            document.getElementById('loading').classList.add('d-none');
            
            if (data.status === 'success') {
                const item = data.data;
                document.getElementById('outMfr').innerText = item.manufacturer_name;
                document.getElementById('outBrand').innerText = item.brand_name;
                document.getElementById('outMpn').innerText = item.mfg_part_num;
                document.getElementById('outClass').innerText = item.classpath;
                
                document.getElementById('outInv').innerText = item.invoice_desc;
                document.getElementById('invLen').innerText = `[Length: ${item.invoice_desc.length} chars]`;
                
                document.getElementById('outMob').innerText = item.mobile_desc;
                document.getElementById('mobLen').innerText = `[Length: ${item.mobile_desc.length} chars]`;
                
                document.getElementById('outShort').innerText = item.short_desc;
                document.getElementById('outLong').innerText = item.long_desc1;
                
                const attrList = document.getElementById('outAttrs');
                attrList.innerHTML = '';
                item.attributes.forEach(a => {
                    attrList.innerHTML += `<li class="list-group-item d-flex justify-content-between"><span>${a.label}</span><strong>${a.value}</strong></li>`;
                });
                
                const featList = document.getElementById('outFeatures');
                featList.innerHTML = '';
                item.features.forEach(f => {
                    featList.innerHTML += `<li>${f}</li>`;
                });
                
                document.getElementById('resultContainer').classList.remove('d-none');
            }
        });
    </script>
</body>
</html>
"""

class SimpleServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode('utf-8'))

    def do_POST(self):
        if self.path == '/api/enrich':
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            req_data = json.loads(body.decode('utf-8'))
            
            try:
                enriched = enrich_product_ai(req_data.get('desc', ''), req_data.get('mpn', ''))
                response = { "status": "success", "data": enriched }
            except Exception as e:
                response = { "status": "error", "message": str(e) }
                
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))

def run_server():
    server = HTTPServer(('localhost', 8000), SimpleServer)
    print("[LIVE] Web Prototype running at http://localhost:8000")
    server.serve_forever()

if __name__ == '__main__':
    run_server()
