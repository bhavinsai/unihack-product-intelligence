import os
import csv
import json
import time
from pydantic import BaseModel, Field
from google import genai
from typing import List

# ---------------------------------------------------------
# 1. DEFINE THE OUTPUT SCHEMA
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

# ---------------------------------------------------------
# 2. THE AI ENRICHMENT ENGINE
# ---------------------------------------------------------
def enrich_product(raw_data: dict, client: genai.Client) -> ProductEnrichment:
    prompt = f"""
    You are an expert industrial product data enricher for a commerce pipeline. 
    Analyze the following messy product data and generate clean, standardized output.
    
    CRITICAL RULES:
    1. INVOICE_DESC must be ALL CAPS and strictly <= 40 characters. Use abbreviations.
    2. MOBILE_DESC must be between 60-80 characters exactly.
    3. Convert decimals to fractions for dimensions (0.5 -> 1/2).
    4. Put spaces between numbers and units (120 V, not 120V).
    
    You MUST respond with ONLY valid JSON matching this exact structure:
    {{
      "manufacturer_name": "Full legal name",
      "brand_name": "Brand name with proper exact casing and ® or ™",
      "mfg_part_num": "Cleaned MPN",
      "classpath": "Category taxonomy path separated by >",
      "invoice_desc": "Max 40 chars, ALL CAPS",
      "mobile_desc": "60-80 chars. Mfr + Brand + Type + Series + MPN",
      "short_desc": "Brand® Series MPN Type + key attributes",
      "long_desc1": "Full technical sentence",
      "retail_desc": "Marketing tone, shorter, no MPN or electrical specs",
      "features": ["feature 1", "feature 2"],
      "attributes": [
        {{"label": "Voltage Rating", "value": "120 V"}},
        {{"label": "Size", "value": "24 in W x 24 in D"}}
      ]
    }}
    
    Do not output any markdown formatting, backticks, or explanation. ONLY raw JSON.

    Raw Input Data:
    {json.dumps(raw_data, indent=2)}
    """
    
    response = client.models.generate_content(
        model='gemini-flash-latest', # Using the model we proved works!
        contents=prompt,
        config={'temperature': 0.1}
    )
    
    # Strip markdown if present to ensure pure JSON
    text = response.text.strip()
    if text.startswith('```json'):
        text = text[7:-3].strip()
    elif text.startswith('```'):
        text = text[3:-3].strip()
        
    data = json.loads(text)
    return ProductEnrichment(**data)

# ---------------------------------------------------------
# 3. CSV BATCH PROCESSING
# ---------------------------------------------------------
def process_csv(input_filepath: str, output_filepath: str):
    client = genai.Client()
    
    # Define the headers we want in our final output file
    output_headers = [
        "Mfg_Part_Num", "Part_Desc", "MANUFACTURER_NAME", "BRAND_NAME", 
        "Classpath", "INVOICE_DESC", "MOBILE_DESC", "SHORT_DESC", 
        "LONG_DESC1", "RETAIL_DESC", "FEATURES", "ATTRIBUTES", "Confidence_Score"
    ]
    
    print(f"Reading from {input_filepath}...")
    
    try:
        with open(input_filepath, mode='r', encoding='utf-8-sig') as infile:
            reader = csv.DictReader(infile)
            
            with open(output_filepath, mode='w', encoding='utf-8-sig', newline='') as outfile:
                writer = csv.DictWriter(outfile, fieldnames=output_headers)
                writer.writeheader()
                
                row_count = 0
                for row in reader:
                    row_count += 1
                    print(f"\nProcessing Row {row_count}: {row.get('Mfg_Part_Num', 'Unknown')}...")
                    
                    try:
                        # Call the AI Engine
                        enriched = enrich_product(row, client)
                        
                        # Format features and attributes into a single string for CSV saving
                        features_str = " | ".join(enriched.features)
                        attributes_str = " | ".join([f"{a.label}: {a.value}" for a in enriched.attributes])
                        
                        # Write the cleaned row to the output CSV
                        writer.writerow({
                            "Mfg_Part_Num": enriched.mfg_part_num,
                            "Part_Desc": row.get('Part_Desc', ''),
                            "MANUFACTURER_NAME": enriched.manufacturer_name,
                            "BRAND_NAME": enriched.brand_name,
                            "Classpath": enriched.classpath,
                            "INVOICE_DESC": enriched.invoice_desc,
                            "MOBILE_DESC": enriched.mobile_desc,
                            "SHORT_DESC": enriched.short_desc,
                            "LONG_DESC1": enriched.long_desc1,
                            "RETAIL_DESC": enriched.retail_desc,
                            "FEATURES": features_str,
                            "ATTRIBUTES": attributes_str,
                            "Confidence_Score": "High" # AI processed successfully
                        })
                        print(f"✅ Success! Saved {enriched.mfg_part_num}")
                        
                        # Wait 2 seconds between rows to avoid hitting API rate limits
                        time.sleep(2)
                        
                    except Exception as e:
                        print(f"❌ Error on row {row_count}: {e}")
                        # If it fails, save the row anyway with a "Needs Review" flag
                        writer.writerow({
                            "Mfg_Part_Num": row.get('Mfg_Part_Num', ''),
                            "Part_Desc": row.get('Part_Desc', ''),
                            "Confidence_Score": "Low - Needs Human Review"
                        })
                        
        print(f"\n🎉 Finished processing! Output saved to {output_filepath}")
        
    except FileNotFoundError:
        print(f"Error: Could not find the file '{input_filepath}'. Make sure it exists!")

def main():
    if not os.environ.get("GEMINI_API_KEY"):
        print("Warning: GEMINI_API_KEY not found in environment. The API call will fail.")
        return
        
    # Set your input and output file names here
    input_file = "input.csv"
    output_file = "final_clean_output.csv"
    
    # If the input file doesn't exist, let's create a dummy one for testing
    if not os.path.exists(input_file):
        print(f"'{input_file}' not found. Creating a test file...")
        with open(input_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Mfg_Part_Num", "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf"])
            writer.writerow(["PDSH4816AF", "PDSH4816AF Dishwasher SS - Display Only", "-- Unbranded --", "-- No Unilog Brand --", "-- No DIB Brand --", "Appliance Dealers Cooperative (APPDE)"])
            writer.writerow(["DCF809D1", "DCF809D1 Dewalt Atomic 20V 1/4\" Impact Driver Kit", "DEWALT", "-- No Unilog Brand --", "-- No DIB Brand --", "Stanley Black & Decker Inc"])
            
    # Run the batch process!
    process_csv(input_file, output_file)

if __name__ == "__main__":
    main()
