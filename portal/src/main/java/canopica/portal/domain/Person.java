package canopica.portal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

@Entity
@Table(name = "person")
public class Person {

    @Id
    private UUID id;

    @Column(name = "first_name", nullable = false)
    private String firstName;

    @Column(name = "last_name", nullable = false)
    private String lastName;

    @Column(name = "date_of_birth", nullable = false)
    private LocalDate dateOfBirth;

    @Column(name = "ssn_token", nullable = false, unique = true)
    private String ssnToken;

    @Column(name = "sex", nullable = false)
    private String sex;

    @Column(name = "is_us_citizen", nullable = false)
    private boolean usCitizen;

    @Column(name = "created_at", insertable = false, updatable = false)
    private Instant createdAt;

    protected Person() {
        // JPA
    }

    public Person(UUID id, String firstName, String lastName, LocalDate dateOfBirth,
                  String ssnToken, String sex, boolean usCitizen) {
        this.id = id;
        this.firstName = firstName;
        this.lastName = lastName;
        this.dateOfBirth = dateOfBirth;
        this.ssnToken = ssnToken;
        this.sex = sex;
        this.usCitizen = usCitizen;
    }

    public UUID getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public LocalDate getDateOfBirth() {
        return dateOfBirth;
    }

    public String getSsnToken() {
        return ssnToken;
    }

    public String getSex() {
        return sex;
    }

    public boolean isUsCitizen() {
        return usCitizen;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
