from flask import Flask, render_template, jsonify
import os

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/servers')
def get_servers():
    # This will be implemented later
    return jsonify([])

@app.route('/api/backgrounds')
def get_backgrounds():
    """Get list of background images from static/background directory"""
    backgrounds = []
    background_dir = os.path.join(app.static_folder, 'background')
    
    # Check if background directory exists
    if os.path.exists(background_dir):
        # Get all files in background directory
        for filename in os.listdir(background_dir):
            # Check if file is an image
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                backgrounds.append(filename)
    
    return jsonify(backgrounds)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
