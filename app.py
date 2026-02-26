import os
import requests
import tempfile
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from werkzeug.utils import secure_filename
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Allowed file extensions
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 
                      'xls', 'xlsx', 'zip', 'rar', '7z', 'mp3', 'mp4', 'avi'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_gofile_server():
    """Get the best Gofile server for upload"""
    try:
        response = requests.get('https://api.gofile.io/servers')
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'ok' and data['data']['servers']:
                # Return the first server (usually the best)
                return data['data']['servers'][0]['name']
    except Exception as e:
        logger.error(f"Error getting server: {str(e)}")
    return 'store1'  # Default fallback server

def upload_to_gofile(file_path, filename):
    """Upload file to Gofile and return direct download link"""
    try:
        # Get best server
        server = get_gofile_server()
        upload_url = f'https://{server}.gofile.io/uploadFile'
        
        # Prepare file for upload
        with open(file_path, 'rb') as f:
            files = {'file': (filename, f, 'application/octet-stream')}
            
            # Upload to Gofile
            response = requests.post(upload_url, files=files)
            
            if response.status_code == 200:
                data = response.json()
                if data['status'] == 'ok':
                    # Extract file info
                    file_data = data['data']
                    
                    # Generate direct download link
                    # Format: https://{server}.gofile.io/download/{fileId}/{filename}
                    direct_link = f"https://{server}.gofile.io/download/{file_data['fileId']}/{filename}"
                    
                    return {
                        'success': True,
                        'direct_link': direct_link,
                        'file_id': file_data['fileId'],
                        'file_name': filename,
                        'size': file_data.get('size', 0),
                        'download_page': file_data['downloadPage']
                    }
            else:
                logger.error(f"Upload failed with status {response.status_code}")
                return {'success': False, 'error': f'Upload failed with status {response.status_code}'}
                
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return {'success': False, 'error': str(e)}
    
    return {'success': False, 'error': 'Unknown upload error'}

@app.route('/')
def index():
    """Render the main upload page"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and return download link"""
    # Check if file was uploaded
    if 'file' not in request.files:
        flash('No file selected')
        return redirect(url_for('index'))
    
    file = request.files['file']
    
    # Check if file is empty
    if file.filename == '':
        flash('No file selected')
        return redirect(url_for('index'))
    
    # Check file type
    if not allowed_file(file.filename):
        flash(f'File type not allowed. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}')
        return redirect(url_for('index'))
    
    try:
        # Secure the filename
        filename = secure_filename(file.filename)
        
        # Save temporarily
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, filename)
        file.save(temp_path)
        
        # Upload to Gofile
        result = upload_to_gofile(temp_path, filename)
        
        # Clean up temp file
        os.remove(temp_path)
        os.rmdir(temp_dir)
        
        if result['success']:
            return render_template('index.html', 
                                 success=True,
                                 direct_link=result['direct_link'],
                                 file_name=result['file_name'],
                                 file_id=result['file_id'],
                                 download_page=result['download_page'])
        else:
            flash(f'Upload failed: {result.get("error", "Unknown error")}')
            return redirect(url_for('index'))
            
    except Exception as e:
        logger.error(f"Error processing upload: {str(e)}")
        flash(f'Error processing upload: {str(e)}')
        return redirect(url_for('index'))

@app.route('/api/upload', methods=['POST'])
def api_upload():
    """API endpoint for programmatic uploads"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'success': False, 'error': 'Empty filename'}), 400
    
    try:
        filename = secure_filename(file.filename)
        
        # Save temporarily
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, filename)
        file.save(temp_path)
        
        # Upload to Gofile
        result = upload_to_gofile(temp_path, filename)
        
        # Clean up
        os.remove(temp_path)
        os.rmdir(temp_dir)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"API upload error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.errorhandler(413)
def too_large(e):
    """Handle file too large error"""
    return jsonify({'success': False, 'error': 'File too large (max 100MB)'}), 413

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
