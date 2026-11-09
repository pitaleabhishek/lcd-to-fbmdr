FROM postgres:17-alpine

RUN apk add --no-cache openssl

COPY ssl-entrypoint.sh /usr/local/bin/ssl-entrypoint.sh
RUN chmod +x /usr/local/bin/ssl-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/ssl-entrypoint.sh"]
CMD ["postgres"]
