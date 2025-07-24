import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Sorter", description="AI-driven intelligent sorting and forwarding for telemetry data")

GROK_API_URL = "https://api.x.ai/v1/chat/completions"
GROK_API_KEY = os.getenv("GROK_API_KEY")

class DataItem(BaseModel):
    type: str
    content: Dict

class BatchRequest(BaseModel):
    items: List[DataItem]

class SortedItem(BaseModel):
    item: DataItem
    category: str
    forward_to: str

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "ai-sorter"}

@app.post("/sort", response_model=List[SortedItem])
async def sort_data(batch: BatchRequest):
    """
    Sort and classify telemetry data using AI API
    """
    if not GROK_API_KEY:
        logger.error("GROK_API_KEY environment variable is not set")
        raise HTTPException(status_code=500, detail="API key missing")

    if not batch.items:
        return []

    try:
        # Build prompt for AI classification
        prompt = """Classify these telemetry items and respond with YAML format:

Instructions:
- Analyze each telemetry item
- Assign category: critical, warning, or info
- Assign forward_to: alerting, storage, or archive
- Critical items with errors/failures should go to alerting
- Warning items should go to storage
- Info items should go to archive

Telemetry items:
"""
        
        for i, item in enumerate(batch.items):
            prompt += f"{i+1}. Type: {item.type}, Content: {str(item.content)[:200]}...\n"
        
        prompt += """
Respond with YAML in this exact format:
```yaml
classifications:
  - category: critical
    forward_to: alerting
  - category: info
    forward_to: storage
```
"""

        # Call Grok API
        response = requests.post(
            GROK_API_URL,
            headers={
                "Authorization": f"Bearer {GROK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "grok-beta",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 1000
            },
            timeout=30
        )

        if response.status_code != 200:
            logger.error(f"AI API error: {response.status_code} - {response.text}")
            raise HTTPException(status_code=500, detail=f"AI API error: {response.status_code}")

        ai_output = response.json()["choices"][0]["message"]["content"]
        logger.info(f"AI API response: {ai_output}")
        
        classifications = parse_ai_output(ai_output)
        
        # Build sorted items
        sorted_items = []
        for i, item in enumerate(batch.items):
            if i < len(classifications):
                cls = classifications[i]
            else:
                # Fallback classification if AI didn't provide enough classifications
                cls = {"category": "info", "forward_to": "storage"}
            
            sorted_items.append(SortedItem(
                item=item,
                category=cls["category"],
                forward_to=cls["forward_to"]
            ))

        logger.info(f"Successfully classified {len(sorted_items)} items")
        return sorted_items

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to communicate with AI API")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

def parse_ai_output(output: str) -> List[Dict]:
    """
    Parse AI output to extract classifications
    """
    import yaml
    import re
    
    try:
        # Extract YAML from markdown code blocks
        yaml_match = re.search(r'```(?:yaml)?\n(.*?)\n```', output, re.DOTALL)
        if yaml_match:
            yaml_content = yaml_match.group(1)
        else:
            yaml_content = output
        
        parsed = yaml.safe_load(yaml_content)
        
        if isinstance(parsed, dict) and "classifications" in parsed:
            return parsed["classifications"]
        elif isinstance(parsed, list):
            return parsed
        else:
            logger.warning("Unexpected AI output format, using fallback")
            return []
            
    except yaml.YAMLError as e:
        logger.error(f"YAML parsing error: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"Error parsing AI output: {str(e)}")
        return []

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)