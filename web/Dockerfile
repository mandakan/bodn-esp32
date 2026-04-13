FROM nginx:1-alpine

RUN rm /etc/nginx/conf.d/default.conf

COPY web/nginx.conf /etc/nginx/conf.d/bodn.conf
COPY web/public/ /usr/share/nginx/html/
COPY assets/nfc/ /usr/share/nginx/html/nfc/

EXPOSE 80
