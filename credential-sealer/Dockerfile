FROM scratch
COPY credential-sealer /credential-sealer
COPY ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
USER 65532:65532
ENV GOTRACEBACK=none
ENTRYPOINT ["/credential-sealer"]
