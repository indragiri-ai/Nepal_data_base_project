import DataFreshness from "./DataFreshness";

export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="inner">
        <div>
          <h3>Nepal Data Portal</h3>
          <p>
            One trustworthy, free home for data about Nepal. Every figure is
            loaded from an official release, archived untouched before
            processing, and shown with its source — nothing is estimated or
            invented by us.
          </p>
        </div>
        <div>
          <h3>Sections</h3>
          <ul>
            <li>
              <a href="/explore">Explore indicators</a>
            </li>
            <li>
              <a href="/banking">Banking &amp; finance</a>
            </li>
          </ul>
        </div>
        <div>
          <h3>Data sources</h3>
          <ul>
            <li>
              <a href="https://data.worldbank.org" target="_blank" rel="noreferrer">
                World Bank — World Development Indicators
              </a>
            </li>
            <li>
              <a
                href="https://www.nrb.org.np/category/monthly-statistics/?department=bfr"
                target="_blank"
                rel="noreferrer"
              >
                Nepal Rastra Bank — Banking &amp; Financial Statistics
              </a>
            </li>
          </ul>
        </div>
      </div>
      <div className="fineprint">
        <DataFreshness />{" "}
        World Bank data is licensed CC&nbsp;BY&nbsp;4.0. NRB figures are provisional as
        published. Charts may be reused with attribution to the original sources.
      </div>
    </footer>
  );
}
