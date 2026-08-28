package canopica.api.notice;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.ArrayList;
import java.util.List;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.pdmodel.font.PDFont;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import org.springframework.stereotype.Component;

/**
 * Renders an approved notice's already-filled {@code content} to PDF bytes (Phase 3 Task 6, design doc
 * §2.4). {@code content} is already fully substituted plain text -- every dollar amount/date came from
 * {@code fill_template}, never the LLM (Task 5's own central mechanism) -- so a direct content-stream write
 * is simpler and has fewer moving parts than an HTML/CSS layout engine this content shape does not need.
 *
 * <p>Per the tradeoffs doc's unrevisited §4.4 ("no records management for the sent artifact"), the rendered
 * bytes are returned, not persisted anywhere -- proving the render pipeline actually produces a valid PDF is
 * this class's whole job, not archival.
 */
@Component
class NoticePdfRenderer {

    private static final PDFont FONT = new PDType1Font(Standard14Fonts.FontName.HELVETICA);
    private static final float FONT_SIZE = 11f;
    private static final float LEADING = 16f;
    private static final float MARGIN = 56f;

    byte[] render(String content) {
        List<String> lines = wrap(content);
        try (PDDocument document = new PDDocument()) {
            writePaginated(document, lines);
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            document.save(out);
            return out.toByteArray();
        } catch (IOException e) {
            throw new UncheckedIOException("failed to render notice content to PDF", e);
        }
    }

    /** Always writes at least one page, even for empty content -- an approved notice must produce a real PDF. */
    private void writePaginated(PDDocument document, List<String> lines) throws IOException {
        float maxY = PDRectangle.LETTER.getHeight() - MARGIN;
        int linesPerPage = (int) ((maxY - MARGIN) / LEADING);
        int start = 0;
        do {
            PDPage page = new PDPage(PDRectangle.LETTER);
            document.addPage(page);
            try (PDPageContentStream stream = new PDPageContentStream(document, page)) {
                stream.beginText();
                stream.setFont(FONT, FONT_SIZE);
                stream.setLeading(LEADING);
                stream.newLineAtOffset(MARGIN, maxY);
                int end = Math.min(start + linesPerPage, lines.size());
                for (String line : lines.subList(start, end)) {
                    stream.showText(line);
                    stream.newLine();
                }
                stream.endText();
            }
            start += linesPerPage;
        } while (start < lines.size());
    }

    /** Wraps on whitespace to the page's own printable width, preserving the template's own blank lines. */
    private List<String> wrap(String content) {
        float maxWidth = PDRectangle.LETTER.getWidth() - 2 * MARGIN;
        List<String> lines = new ArrayList<>();
        for (String paragraph : content.split("\n", -1)) {
            if (paragraph.isEmpty()) {
                lines.add("");
                continue;
            }
            StringBuilder current = new StringBuilder();
            for (String word : paragraph.split(" ")) {
                String candidate = current.isEmpty() ? word : current + " " + word;
                if (!current.isEmpty() && width(candidate) > maxWidth) {
                    lines.add(current.toString());
                    current = new StringBuilder(word);
                } else {
                    current = new StringBuilder(candidate);
                }
            }
            lines.add(current.toString());
        }
        return lines;
    }

    private float width(String text) {
        try {
            return FONT.getStringWidth(text) / 1000 * FONT_SIZE;
        } catch (IOException e) {
            throw new UncheckedIOException("failed to measure notice text width", e);
        }
    }
}
