# Dockerfile for Municipal Transit Incident Report (DATA-260 HW1)
# Serves the static HTML/CSS/JS app via nginx on PORT_BASE (8446)

FROM nginx:alpine

# Remove default nginx static content
RUN rm -rf /usr/share/nginx/html/*

# Copy our web application files into nginx's serving directory
COPY index.html /usr/share/nginx/html/
COPY script.js /usr/share/nginx/html/

# Configure nginx to listen on our assigned PORT_BASE instead of default 80
RUN sed -i 's/listen\s*80;/listen 8446;/' /etc/nginx/conf.d/default.conf

EXPOSE 8446

CMD ["nginx", "-g", "daemon off;"]
