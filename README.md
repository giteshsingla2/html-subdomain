# subdomain-flask-city-script


Required Json: 
 {
    "Business Name": "",
    "Business Address": "",
    "Business Phone Number": "",
    "Business Logo": "",
    "Business Email": "",
    "Main Service" : "",
    "Favicon": ""
 }
 
Main Service Page Json {
 {
    "Title": "",
    "Meta Description": "",
    "Long Description [For Hero Section]": "",
    "Image 1": "",
    "Image 1 Alt": "",
    "Image 2": "",
    "Image 2 Alt": "",
    "About Content [HTML Format Paragraph]": "",
    "Why Choose Us Content Listicle [HTML Format]": "",
    "Blog Content [HTML Format]": "",
    "Our Process": "",
    "Reviews [5-6 Json Format]": [
      {
        "name": "",
        "review": ""
      },
      {
        "name": "",
        "review": ""
      }
    ],
    "FAQ": [
      {
        "Question": "",
        "Answer": ""
      },
      {
        "Question": "",
        "Answer": ""
      }
    ],
    "CTA Title and Description": {
      "Title": "",
      "Description": ""
    }
  }
}

  Service Json {
{"Service 1": {
    "Title": "",
    "Meta Description": "",
    "Blog Content": "",
    "Reviews": [
      {
        "name": "",
        "review": ""
      },
      {
        "name": "",
        "review": ""
      }
    ],
    "FAQ": [
      {
        "Question": "",
        "Answer": ""
      },
      {
        "Question": "",
        "Answer": ""
      }
    ],
    "CTA Title and Description": {
      "Title": "",
      "Description": ""
    }
}
Service 2: {
    "Title": "",
    "Meta Description": "",
    "Blog Content": "",
    "Reviews": [
      {
        "name": "",
        "review": ""
      },
      {
        "name": "",
        "review": ""
      }
    ],
    "FAQ": [
      {
        "Question": "",
        "Answer": ""
      },
      {
        "Question": "",
        "Answer": ""
      }
    ],
    "CTA Title and Description": {
      "Title": "",
      "Description": ""
    }
}

  }
  }



server {
    listen 80;
    server_name dhanwantaritemple.in www.dhanwantaritemple.in;
    root /var/www/yourapp;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    server_name *.dhanwantaritemple.in;
    root /var/www/yourapp;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
