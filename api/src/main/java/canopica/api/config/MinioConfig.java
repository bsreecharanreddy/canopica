package canopica.api.config;

import java.net.URI;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

/**
 * MinIO is S3-compatible (Phase 3 design doc §2.1), so the standard AWS SDK v2 client works against it
 * unmodified -- an endpoint override plus path-style access (MinIO has no per-bucket subdomain DNS the way
 * real S3 does) is the only difference from a real-AWS client. The region is a required SDK parameter MinIO
 * itself ignores, not a real region choice.
 */
@Configuration
class MinioConfig {

    @Bean
    S3Client s3Client(
            @Value("${canopica.minio.endpoint}") String endpoint,
            @Value("${canopica.minio.access-key}") String accessKey,
            @Value("${canopica.minio.secret-key}") String secretKey) {
        return S3Client.builder()
                .endpointOverride(URI.create(endpoint))
                .credentialsProvider(StaticCredentialsProvider.create(AwsBasicCredentials.create(accessKey, secretKey)))
                .region(Region.US_EAST_1)
                .forcePathStyle(true)
                .build();
    }
}
