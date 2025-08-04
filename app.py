from flask import Flask, request, send_file, jsonify
import json
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import io
from io import BytesIO
import os
import uuid
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
app = Flask(__name__)

# Thread-local storage for request isolation
local_data = threading.local()

# Configuration
POSITIONS_CONFIG = {
    "images": [
        {"path": "lwf.png", "x": 300, "y": 40},
        {"path": "rb.png", "x": 836, "y": 370},
        {"path": "cb2.png", "x": 706, "y": 420},
        {"path": "rwf.png", "x": 836, "y": 40},
        {"path": "cf.png", "x": 568, "y": 15},
        {"path": "lb.png", "x": 300, "y": 370},
        {"path": "cb1.png", "x": 435, "y": 420},
        {"path": "amf1.png", "x": 430, "y": 170},
        {"path": "dmf.png", "x": 568, "y": 300},
        {"path": "amf2.png", "x": 706, "y": 170},
        {"path": "gk.png", "x": 570, "y": 460}
    ]
}

# Styling Settings
SCALE_FACTOR = 0.40
CORNER_RADIUS = 14
BORDER_WIDTH = 3
BORDER_COLOR = (173, 216, 230, 100)  # Light blue with alpha
TEXT_COLOR = (255, 255, 0, 255)  # Yellow
FONT_SIZE = 46
TEXT_X = 1040
TEXT_Y = 123

def download_image(url, request_id):
    """Download image from URL and return PIL Image object"""
    try:
        # Add headers to mimic a real browser request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, timeout=15, headers=headers)
        response.raise_for_status()
        
        # Get the image data
        image_data = response.content
        
        # Try to open the image
        img = Image.open(io.BytesIO(image_data))
        
        # Get original format for logging
        original_format = img.format or "Unknown"
        print(f"[{request_id}] Downloaded {original_format} image from {url}")
        
        # Handle different image modes
        if img.mode == 'RGBA':
            # Already has transparency, keep as is
            return img
        elif img.mode == 'RGB':
            # Convert RGB to RGBA (add alpha channel)
            return img.convert('RGBA')
        elif img.mode == 'P':
            # Palette mode - check if it has transparency
            if 'transparency' in img.info:
                # Convert palette with transparency to RGBA
                return img.convert('RGBA')
            else:
                # Convert palette without transparency to RGBA
                return img.convert('RGB').convert('RGBA')
        elif img.mode == 'L':
            # Grayscale - convert to RGBA
            return img.convert('RGB').convert('RGBA')
        elif img.mode == 'LA':
            # Grayscale with alpha - convert to RGBA
            return img.convert('RGBA')
        elif img.mode == '1':
            # 1-bit pixels - convert to RGBA
            return img.convert('RGB').convert('RGBA')
        elif img.mode == 'CMYK':
            # CMYK mode - convert to RGB then RGBA
            return img.convert('RGB').convert('RGBA')
        else:
            # Any other mode - try to convert to RGBA
            print(f"[{request_id}] Unknown image mode: {img.mode}, attempting conversion")
            return img.convert('RGBA')
            
    except requests.exceptions.RequestException as e:
        print(f"[{request_id}] Network error downloading image from {url}: {e}")
        return None
    except Image.UnidentifiedImageError as e:
        print(f"[{request_id}] Invalid image format from {url}: {e}")
        return None
    except Exception as e:
        print(f"[{request_id}] Unexpected error downloading image from {url}: {e}")
        return None

def validate_image_url(url):
    """Validate if URL points to a supported image format"""
    try:
        parsed_url = urlparse(url)
        if not parsed_url.scheme in ['http', 'https']:
            return False
        
        # Check file extension (not foolproof but helps filter obvious non-images)
        supported_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.ico'}
        path = parsed_url.path.lower()
        
        # If there's an extension, check if it's supported
        if '.' in path:
            ext = '.' + path.split('.')[-1]
            return ext in supported_extensions
        
        # If no extension, we'll let the download attempt proceed
        # (some URLs don't have extensions but serve images)
        return True
        
    except Exception:
        return False

def download_images_parallel(url_params, request_id):
    """Download multiple images in parallel with format validation"""
    downloaded_images = {}
    
    # First, validate all URLs
    valid_urls = {}
    for key, url in url_params.items():
        if validate_image_url(url):
            valid_urls[key] = url
        else:
            print(f"[{request_id}] Skipping invalid URL for {key}: {url}")
    
    def download_single(key_url_pair):
        key, url = key_url_pair
        print(f"[{request_id}] Downloading {key} from {url}")
        img = download_image(url, request_id)
        return key, img
    
    # Use ThreadPoolExecutor for parallel downloads
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(download_single, valid_urls.items())
        
        for key, img in results:
            if img is not None:
                downloaded_images[key] = img
    
    return downloaded_images
    """Download multiple images in parallel"""
    downloaded_images = {}
    
    def download_single(key_url_pair):
        key, url = key_url_pair
        print(f"[{request_id}] Downloading {key} from {url}")
        img = download_image(url, request_id)
        return key, img
    
    # Use ThreadPoolExecutor for parallel downloads
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(download_single, url_params.items())
        
        for key, img in results:
            if img is not None:
                downloaded_images[key] = img
    
    return downloaded_images

def process_image(img, x, y, request_id):
    """Process individual image with scaling, cropping, and styling"""
    try:
        # Resize image
        new_size = (int(img.width * SCALE_FACTOR), int(img.height * SCALE_FACTOR))
        img = img.resize(new_size, resample=Image.LANCZOS)
        
        # Get dimensions
        width, height = img.size
        
        # Crop top square
        square_height = min(width, height)
        cropped_img = img.crop((0, 0, width, square_height))
        
        # Create transparent base with space for border
        decorated_size = (width + BORDER_WIDTH * 2, square_height + BORDER_WIDTH * 2)
        decorated_img = Image.new("RGBA", decorated_size, (0, 0, 0, 0))
        
        # Draw light blue rounded border
        border_draw = ImageDraw.Draw(decorated_img)
        border_draw.rounded_rectangle(
            [0, 0, decorated_size[0], decorated_size[1]],
            radius=CORNER_RADIUS + BORDER_WIDTH,
            fill=BORDER_COLOR
        )
        
        # Create mask for rounded corners
        mask = Image.new("L", cropped_img.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle(
            [0, 0, width, square_height],
            radius=CORNER_RADIUS,
            fill=255
        )
        
        # Paste cropped image onto border
        decorated_img.paste(cropped_img, (BORDER_WIDTH, BORDER_WIDTH), mask=mask)
        
        return decorated_img
    except Exception as e:
        print(f"[{request_id}] Error processing image: {e}")
        return None

@app.route('/generate', methods=['GET'])
def generate_image():
    # Generate unique request ID for this request
    request_id = str(uuid.uuid4())[:8]
    
    try:
        print(f"[{request_id}] Starting image generation request")
        
        # Load base background image (create a copy for this request)
        if not os.path.exists("image.png"):
            return jsonify({"error": "Background image 'image.png' not found"}), 404
        
        bg = Image.open("image.png").convert("RGBA").copy()
        
        # Get URL parameters with validation
        url_params = {}
        invalid_params = []
        
        for key, value in request.args.items():
            if key.startswith(('ss', 'amf', 'cf', 'dmf', 'gk', 'lb', 'rb', 'cb', 'lwf', 'rwf')):
                if validate_image_url(value):
                    url_params[key] = value
                else:
                    invalid_params.append(f"{key}={value}")
        
        if invalid_params:
            print(f"[{request_id}] Found invalid image URLs: {', '.join(invalid_params)}")
        
        # Get text parameter
        text = request.args.get('text', '3126')
        
        print(f"[{request_id}] Found {len(url_params)} image URLs to download")
        
        # Download all images in parallel
        downloaded_images = download_images_parallel(url_params, request_id)
        
        print(f"[{request_id}] Successfully downloaded {len(downloaded_images)} images")
        
        # Process each image from the positions config
        processed_count = 0
        for item in POSITIONS_CONFIG["images"]:
            path = item["path"]
            x = item["x"]
            y = item["y"]
            
            # Extract the key from the filename (remove .png extension)
            key = os.path.splitext(path)[0]
            
            img = None
            
            # Check if we have a downloaded image for this position
            if key in downloaded_images:
                img = downloaded_images[key]
                print(f"[{request_id}] Using downloaded image for {key}")
            else:
                # Try to load local image as fallback
                if os.path.exists(path):
                    img = Image.open(path).convert("RGBA").copy()
                    print(f"[{request_id}] Using local fallback image for {key}")
                else:
                    print(f"[{request_id}] No image found for position {key}")
                    continue  # Skip if no URL provided and no local file
            
            # Process and paste the image
            decorated_img = process_image(img, x, y, request_id)
            if decorated_img:
                bg.paste(decorated_img, (x, y), decorated_img)
                processed_count += 1
        
        print(f"[{request_id}] Processed {processed_count} images")
        
        # Add text
        try:
            font = ImageFont.truetype("arial.ttf", FONT_SIZE)
        except:
            try:
                font = ImageFont.truetype("arial.otf", FONT_SIZE)
            except:
                font = ImageFont.load_default()
        
        draw = ImageDraw.Draw(bg)
        draw.text((TEXT_X, TEXT_Y), str(text), font=font, fill=TEXT_COLOR)
        
        # Save to memory buffer
        img_buffer = io.BytesIO()
        bg.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        print(f"[{request_id}] Image generation completed successfully")
        
        return send_file(
            img_buffer,
            mimetype='image/png',
            as_attachment=False,
            download_name=f'generated_image_{request_id}.png'
        )
        
    except Exception as e:
        print(f"[{request_id}] Error occurred: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}", "request_id": request_id}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "message": "API is running"})

BANNER_URL = "https://files.catbox.moe/wn4cbr.jpeg"

@app.route("/vimage", methods=["GET"])
def overlay_image():
    overlay_url = request.args.get("img")  # Only overlay is passed
    if not overlay_url:
        return jsonify({"error": "Missing 'img' parameter"}), 400

    # Generate unique request ID for logging
    request_id = str(uuid.uuid4())[:8]
    temp_path = None
    
    try:
        print(f"[{request_id}] Starting vimage generation with overlay: {overlay_url}")
        
        # Validate URLs
        if not validate_image_url(overlay_url):
            return jsonify({"error": "Invalid overlay image URL"}), 400
        
        # Headers to mimic real browser request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        # Download banner image with better error handling
        print(f"[{request_id}] Downloading banner from: {BANNER_URL}")
        try:
            banner_response = requests.get(BANNER_URL, timeout=15, headers=headers, stream=True)
            banner_response.raise_for_status()
            base_img = Image.open(BytesIO(banner_response.content)).convert("RGBA")
            print(f"[{request_id}] Banner downloaded successfully")
        except requests.exceptions.RequestException as e:
            print(f"[{request_id}] Failed to download banner: {e}")
            return jsonify({"error": f"Failed to download banner image: {str(e)}"}), 500
        except Exception as e:
            print(f"[{request_id}] Failed to process banner: {e}")
            return jsonify({"error": f"Failed to process banner image: {str(e)}"}), 500

        # Download overlay image with better error handling
        print(f"[{request_id}] Downloading overlay from: {overlay_url}")
        try:
            overlay_response = requests.get(overlay_url, timeout=15, headers=headers, stream=True)
            overlay_response.raise_for_status()
            overlay_img = Image.open(BytesIO(overlay_response.content)).convert("RGBA")
            print(f"[{request_id}] Overlay downloaded successfully")
        except requests.exceptions.RequestException as e:
            print(f"[{request_id}] Failed to download overlay: {e}")
            return jsonify({"error": f"Failed to download overlay image: {str(e)}"}), 500
        except Exception as e:
            print(f"[{request_id}] Failed to process overlay: {e}")
            return jsonify({"error": f"Failed to process overlay image: {str(e)}"}), 500

        # Reduce overlay size
        scale_factor = 0.7  # Reduced from 1.3 to 0.7 to make overlay smaller
        new_size = (int(overlay_img.width * scale_factor), int(overlay_img.height * scale_factor))
        overlay_img = overlay_img.resize(new_size, Image.LANCZOS)

        # Create blue-tinted glow
        glow = overlay_img.copy()
        blue_layer = Image.new("RGBA", glow.size, (0, 0, 255, 180))  # Blue with alpha
        glow = Image.alpha_composite(glow, blue_layer)
        glow = glow.filter(ImageFilter.GaussianBlur(30))  # Stronger blur for glow

        # Compute position (center)
        x = (base_img.width - overlay_img.width) // 2
        y = (base_img.height - overlay_img.height) // 2

        # Paste glow then overlay
        base_img.paste(glow, (x, y), glow)
        base_img.paste(overlay_img, (x, y), overlay_img)

        # Create temp file with proper cleanup
        temp_path = tempfile.mktemp(suffix=".png")
        base_img.save(temp_path, "PNG")
        
        print(f"[{request_id}] Image processing completed successfully")

        # Use a custom response that handles file cleanup
        def remove_file(response):
            try:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
            except:
                pass
            return response

        response = send_file(
            temp_path, 
            mimetype="image/png", 
            as_attachment=False,  # Changed to False for better browser compatibility
            download_name="vimage_output.png"
        )
        
        # Schedule file cleanup after response is sent
        @response.call_on_close
        def cleanup():
            try:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
                    print(f"[{request_id}] Temporary file cleaned up")
            except Exception as e:
                print(f"[{request_id}] Error cleaning up temp file: {e}")
        
        return response

    except Exception as e:
        print(f"[{request_id}] Unexpected error in vimage route: {str(e)}")
        
        # Clean up temp file in case of error
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        
        return jsonify({
            "error": f"An error occurred: {str(e)}", 
            "request_id": request_id
        }), 500

@app.route('/', methods=['GET'])
def info():
    return jsonify({
        "message": "Dynamic Image Generator API",
        "usage": "/generate?ss=<url>&amf1=<url>&text=<text>",
        "example": "/generate?ss=https://files.catbox.moe/heheh.png&amf1=https://files.catbox.moe/hbvey.jpg&text=3167",
        "supported_positions": [item["path"].replace('.png', '') for item in POSITIONS_CONFIG["images"]],
        "supported_formats": ["JPG/JPEG", "PNG", "GIF", "BMP", "TIFF", "WebP", "ICO"],
        "notes": [
            "Images are automatically converted to RGBA format",
            "Transparency is preserved where supported",
            "Invalid URLs are skipped with fallback to local images"
        ]
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=7860)
