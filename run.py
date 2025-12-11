import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    # Debug mode should be disabled in production. 
    # Use an environment variable to enable it only for development.
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() in ['true', '1', 't']
    app.run(host='0.0.0.0', port=5000, debug=True)
