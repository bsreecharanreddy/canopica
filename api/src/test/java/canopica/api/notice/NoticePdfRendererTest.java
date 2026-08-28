package canopica.api.notice;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.text.PDFTextStripper;
import org.junit.jupiter.api.Test;

/**
 * Proves the render pipeline produces a real, parseable PDF, not just non-empty bytes -- reads the rendered
 * document back with PDFBox's own text stripper rather than trusting {@code render}'s own library calls
 * succeeded, the same "verify for real" bar this project holds everywhere else.
 */
class NoticePdfRendererTest {

    private final NoticePdfRenderer renderer = new NoticePdfRenderer();

    @Test
    void rendersShortContentToASinglePageContainingItsOwnText() throws IOException {
        byte[] pdf = renderer.render("Dear Sam Applicant,\n\nYour benefit is $170.00.");

        assertThat(pdf).isNotEmpty();
        try (PDDocument document = Loader.loadPDF(pdf)) {
            assertThat(document.getNumberOfPages()).isEqualTo(1);
            String text = new PDFTextStripper().getText(document);
            assertThat(text).contains("Sam Applicant").contains("$170.00");
        }
    }

    @Test
    void wrapsALongLineRatherThanCuttingItOff() throws IOException {
        String longWord = "word ".repeat(200).trim();
        byte[] pdf = renderer.render(longWord);

        try (PDDocument document = Loader.loadPDF(pdf)) {
            String text = new PDFTextStripper().getText(document).replaceAll("\\s+", " ").trim();
            assertThat(text).isEqualTo(longWord);
        }
    }

    @Test
    void spillsOntoASecondPageWhenContentExceedsOnePage() throws IOException {
        String manyLines = "A line of notice content.\n".repeat(100);
        byte[] pdf = renderer.render(manyLines);

        try (PDDocument document = Loader.loadPDF(pdf)) {
            assertThat(document.getNumberOfPages()).isGreaterThan(1);
        }
    }

    @Test
    void rendersEmptyContentAsOneValidBlankPageRatherThanFailing() throws IOException {
        byte[] pdf = renderer.render("");

        assertThat(pdf).isNotEmpty();
        try (PDDocument document = Loader.loadPDF(pdf)) {
            assertThat(document.getNumberOfPages()).isEqualTo(1);
        }
    }
}
