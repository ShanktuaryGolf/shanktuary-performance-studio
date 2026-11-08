# Studio connections (local development build)

Open **Tools → Shot source** (Connection) or the startup guided setup. Choose Nova,
GSPro, PurePlay, or Other connector. Experimental Common Golf Protocol is under Advanced.
Selecting **Another launch monitor** opens its setup and starts local listening
immediately. Nova and CGP retain their explicit **Connect** action; GSPro retains
**Start Reading**. A valid new test shot is required before entering the session. Back/close/stop cancels the input; choosing another source
invalidates queued events from the old source. No source auto-starts on launch.
Existing `both` configuration remains a compatibility mode, not a wizard choice.

## PurePlay (experimental local files)

Choose **Use PurePlay**, select its **Profiles** folder if it is not detected,
and click **Start Reading** before hitting a new shot. Studio reads schema-1
`<profile>/shots/session-*.json` files without changing PurePlay data. Existing
history is skipped. Valid newly saved shots are accepted independently of the
input hardware; input flags are retained but do not certify measurements.

PurePlay launch values are source-reported, while its carry, total and apex are
source estimates. Optional OpenGolfCoach fills only supported missing fields;
its output is labelled modelled/derived, never measured. Unverified raw club and
impact values are retained as metadata rather than presented as measured values.
The Overview and Club pages use the same layouts as Nova with presence-aware
values and geometry. No missing value is silently replaced with zero.

Live ingestion was checked with Nova feeding PurePlay on Windows. Other hardware,
PurePlay versions and spin/launch sign conventions are not independently verified.
This is not an official PurePlay API or a guarantee of monitor compatibility.

## Open Connect

This is a GSPro-style TCP JSON receiver, not a GSPro database connection. Default
port is 921. The normal flow needs no address entry or extra Start button: open
your usual connector and choose its GSPro / Open Connect output, if available.
Compatibility and output names vary by connector/version. Springbok, RELA and
other compatible connectors share this method, not separate source modes.

**Advanced connection settings** retains the port and local/network choices.
Fresh setups default to loopback. A previously explicit Advanced network setting
is preserved, and the screen clearly identifies active network listening.
Explicitly choose the network option and Apply to listen on all IPv4 interfaces. The latter exposes the receiver
to the local network only while started. No firewall or system security changes
are made. Alternate ports only work if the connector supports configuring them.
A port-in-use error may mean GSPro or another app owns the port; Studio does not
assert which process owns it. Close the competing receiver or use a supported
alternate port in Advanced. Listening, connector connection and accepted shot
readiness are distinct; a socket connection alone never unlocks Start Session.
Only `Yards`/mph legacy messages are accepted; unsupported units return an error.
Messages are bounded, strictly parsed, and deduplicated per device/shot number.
Stop/start begins a new session; TCP reconnect alone does not reset deduplication.

## Common Golf Protocol (experimental)

Pinned specification: OpenLaunchLabs/common-golf-protocol commit
`1c343a8aac2b21665e9ce002789dfcc98abe133f`, Draft 2 / 0.2.0.
Discovery uses `_common-golf._udp.local.`; QUIC ALPN is `common-golf/draft-2`.
Studio consumes final ball shots only. Preliminary measurements and late club
messages do not create duplicate history, pressure captures or calibration shots.
Unsupported channels are declined. Missing values and signed topspin remain intact.
A shared bounded measurement-ID cache prevents replay across reconnects; without a
measurement ID, reliable deduplication across a device restart is not guaranteed.

The initial consumer does not supply an optional connector certificate. It uses
the protocol's ephemeral device identity, does not enroll credentials or persist
private keys, and does not provide authenticated device trust. Connect only on a
trusted network. No upstream private TLS monkeypatches are used. Peer fingerprint
status is informational rather than a trust enrollment. Reconnect is explicit.

## Optional local OpenGolfCoach

`opengolfcoach==0.3.0` is pinned. Enrichment and speculative club estimates are
separate, default-off choices. Only missing fields are added: sender values,
including zero, always win. Per-field metadata records provenance, method/version,
inputs and model assumptions. Source-reported values are not automatically called
measured; CGP source estimates remain labelled estimates. Modeled/estimated fields
are labelled in UI/export and excluded from calibration ground truth.

Flight modelling requires actual ball speed, vertical/horizontal launch and a
complete supported spin vector. Missing inputs are not replaced with zero. CGP
negative topspin is preserved but is not modelled by OGC because its convention is
unsupported. No spin, attack angle, dynamic loft, or impact-location values are
invented. Club modelling is speculative (including a fixed 200 g head assumption),
not a measured club sensor. OGC default environment assumptions are recorded.

Official native wheels exist for supported Windows/Linux x64 and Apple Silicon
configurations. Intel macOS has no OGC 0.3.0 wheel; installation omits this optional
dependency and enrichment reports unavailable. Source connections remain usable.

## Development verification and safe screenshots

Tests exercise real TCP/QUIC on loopback, including the pinned reference device,
real local OGC, generation races, replay, strict parsing, data provenance and UI
navigation. Headless rendering tests do not replace platform/hardware testing.

`SPS_UI_PREVIEW=1 python shanktuary_app.py --splash` runs the actual application
with pressure hardware and the OBS listener disabled. It does not simulate shots
or connection readiness. Use an isolated HOME/data profile for screenshots.
The flag is for UI inspection only, not normal play. Open Connect can still be
started explicitly for a loopback test; never represent a fixture as hardware.

Release packages are built from the versioned source after repository-backed
CI tests and platform builds pass. Hardware verification remains limited to the
scenarios explicitly described above.
