# Keycloak for Cloud Run (core-007 FR-012, FR-015): free open-source edition, production mode,
# no database (embedded dev-file store, rebuilt at every start). The realm, roles and accounts are
# imported at start from /opt/keycloak/data/import/realm-pharmagentics.json, which Cloud Run mounts
# from Secret Manager (rendered by deploy/gcp.py with the passwords filled in).
FROM quay.io/keycloak/keycloak:26.4 AS build
ENV KC_DB=dev-file KC_HEALTH_ENABLED=true
RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.4
COPY --from=build /opt/keycloak/ /opt/keycloak/
# Cloud Run terminates TLS and forwards X-Forwarded-* headers; KC_HOSTNAME is set at deploy time.
ENV KC_HTTP_ENABLED=true KC_HTTP_PORT=8080 KC_PROXY_HEADERS=xforwarded
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
CMD ["start", "--optimized", "--import-realm"]
