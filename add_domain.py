import subprocess
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/add-domain', methods=['POST'])
def add_domain():
    data = request.json
    domain_name = data.get('domain_name')
    if not domain_name:
        return jsonify({"error": "Domain name is required"}), 400

    try:
        # 1) Create your site directory
        subprocess.run(
            ['sudo','mkdir','-p',f'/var/www/html-subdomain/domains/{domain_name}'],
            check=True
        )
        subprocess.run(
            ['sudo','chown','-R','www-data:www-data',
             f'/var/www/html-subdomain/domains/{domain_name}/'],
            check=True
        )
        subprocess.run(
            ['sudo','find',
             f'/var/www/html-subdomain/domains/{domain_name}/',
             '-type','d','-exec','chmod','755','{}',';'],
            check=True
        )
        subprocess.run(
            ['sudo','find',
             f'/var/www/html-subdomain/domains/{domain_name}/',
             '-type','f','-exec','chmod','644','{}',';'],
            check=True
        )

        # 2) Write a fresh nginx vhost file
        nginx_conf = f"""
server {{
    listen 80;
    server_name {domain_name} www.{domain_name};
    root /var/www/html-subdomain;

    location / {{
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}

server {{
    listen 80;
    server_name *.{domain_name};
    root /var/www/html-subdomain;

    location / {{
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
""".strip()

        conf_path = f'/etc/nginx/sites-available/{domain_name}'
        # write the new nginx config
        with open(conf_path, 'w') as f:
            f.write(nginx_conf)

        # 3) Enable & reload nginx
        subprocess.run(['sudo','ln','-sf',
                        conf_path,
                        f'/etc/nginx/sites-enabled/{domain_name}'],
                       check=True)
        subprocess.run(['sudo','nginx','-t'], check=True)
        subprocess.run(['sudo','systemctl','reload','nginx'], check=True)

        return jsonify({"message": f"Domain {domain_name} added successfully"}), 200

    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5035)
