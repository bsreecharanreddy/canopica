# Build context is the repo root (portal depends on the rules-engine
# module in the same Maven reactor -- see the root pom.xml's <modules>),
# so this only COPYs the paths the reactor build actually needs, not all
# of portal/ (which also holds the unrelated portal/web npm project).
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY pom.xml mvnw ./
COPY .mvn .mvn
COPY rules-engine rules-engine
COPY portal/pom.xml portal/pom.xml
COPY portal/src portal/src
RUN ./mvnw -B -q -pl portal -am package -DskipTests

FROM eclipse-temurin:17-jre
# curl backs the healthcheck below -- not present in the base -jre image.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /workspace/portal/target/portal-*.jar app.jar
EXPOSE 8080
# 127.0.0.1, not localhost -- see portal/web/Dockerfile's healthcheck
# comment for the ::1-vs-0.0.0.0 resolution gotcha this sidesteps; this one
# happened to resolve to IPv4 fine on glibc, but pin it anyway rather than
# rely on resolver-order luck.
HEALTHCHECK --interval=10s --timeout=5s --retries=12 --start-period=30s \
    CMD curl -f http://127.0.0.1:8080/actuator/health || exit 1
ENTRYPOINT ["java", "-jar", "app.jar"]
