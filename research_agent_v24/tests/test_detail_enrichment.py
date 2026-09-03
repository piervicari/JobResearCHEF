from research_agent.pipeline.detail_enrichment import parse_detail_html


def test_parse_detail_html_prefers_jobposting_json_ld():
    html = '''
    <html><body><script type="application/ld+json">
    {
      "@context":"https://schema.org",
      "@type":"JobPosting",
      "title":"Threat Intelligence Analyst",
      "description":"<p>Investigate threats and produce intelligence.</p>",
      "employmentType":"FULL_TIME",
      "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress","addressLocality":"Rome","addressCountry":"IT"}}
    }
    </script></body></html>
    '''
    parsed = parse_detail_html(html, final_url="https://example.test/job/1")
    assert parsed.title == "Threat Intelligence Analyst"
    assert "Investigate threats" in parsed.description
    assert parsed.city == "Rome"
    assert parsed.country == "IT"
    assert parsed.parser == "json_ld_jobposting"


def test_parse_detail_html_falls_back_to_main_text_and_labels():
    html = '''
    <html><body><main>
      <div>Security · Stockholm · Hybrid</div>
      <h1>Cyber Security Solutions Engineer</h1>
      <p>Work with customers on application security and vulnerability findings.</p>
      <h2>Locations</h2><div>Stockholm</div>
      <h2>Employment type</h2><div>Full-time</div>
    </main></body></html>
    '''
    parsed = parse_detail_html(html, final_url="https://example.test/jobs/1")
    assert parsed.title == "Cyber Security Solutions Engineer"
    assert parsed.location == "Stockholm"
    assert parsed.employment_type == "Full-time"
    assert "application security" in parsed.description
    assert parsed.parser == "main_text"
