import base64
from openai import OpenAI
from paddleocr import PaddleOCR

client = OpenAI(api_key="sk-anything", base_url="http://localhost:4000")

def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def get_ocr_text(image_path):
    # Updated to the stable PaddleOCR 2.7.3 setup
    ocr = PaddleOCR(
        use_angle_cls=True, 
        lang='en', 
        use_gpu=False, 
        enable_mkldnn=False
    )
    results = ocr.ocr(image_path, cls=True)
    
    lines = []
    if results and results[0]:
        for line in results[0]:
            # Extracts just the text portion from the result array
            text = line[1][0]
            lines.append(text)
            
    return ", ".join(lines)

def get_vision_description(image_path, ocr_text):
    image_b64 = encode_image(image_path)
    response = client.chat.completions.create(
        model="vision",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "OCR has already extracted these exact text labels from from image: "
                            f"{ocr_text}\n\n"
                            "Using these labels as ground truth,"
                            "describe the overall process flow"
                            "and what role each major component plays. "
                            "Do not invent component names that aren't in the OCR list or clearly implied by it."
                        )
                    },
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }
        ]
    )
    return response.choices[0].message.content
if __name__ == "__main__":
    image_path = "images.jpg"

    print("Running OCR...")
    ocr_text = get_ocr_text(image_path)
    print(f"OCR labels found: {ocr_text}\n")

    print("Running vision model (grounded with OCR labels)...")
    vision_desc = get_vision_description(image_path, ocr_text)
    print(f"Vision description:\n{vision_desc}\n")

    combined_context = f"""OCR-extracted labels from the diagram: {ocr_text}

Vision model's structural interpretation (grounded with OCR labels): {vision_desc}"""

    with open("combined_context.txt", "w", encoding="utf-8") as f:
        f.write(combined_context)

    print("Saved combined context to combined_context.txt")