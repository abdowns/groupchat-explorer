use base64::{engine::general_purpose::STANDARD, Engine as _};
use imessage_database::{
    message_types::variants::{Tapback, TapbackAction, Variant},
    tables::{
        attachment::Attachment,
        capabilities::Capabilities,
        messages::{models::BubbleComponent, Message},
        table::{get_connection, Table},
    },
    util::query_context::QueryContext,
};
use rusqlite::Connection;
use serde_json::{json, Value};
use std::{
    collections::{BTreeSet, HashMap},
    env,
    io::{self, BufWriter, Write},
    path::Path,
};

fn timestamp(value: i64) -> f64 {
    (if value.abs() >= 1_000_000_000_000 {
        value as f64 / 1e9
    } else {
        value as f64
    }) + 978307200.0
}
// Keyed archives can contain UIDs, which plist XML cannot represent. Never
// emit the partially written XML buffer if serialization fails.
fn encode_payload(
    payload: &plist::Value,
) -> Result<(Option<String>, Option<String>), plist::Error> {
    let mut xml = Vec::new();
    if payload.to_writer_xml(&mut xml).is_ok() {
        return Ok((Some(String::from_utf8_lossy(&xml).into_owned()), None));
    }
    let mut binary = Vec::new();
    payload.to_writer_binary(&mut binary)?;
    Ok((None, Some(STANDARD.encode(binary))))
}

fn emit(out: &mut impl Write, value: Value) -> io::Result<()> {
    serde_json::to_writer(&mut *out, &value)?;
    out.write_all(b"\n")
}
fn handles(db: &Connection) -> rusqlite::Result<HashMap<i32, String>> {
    db.prepare("SELECT ROWID,id FROM handle")?
        .query_map([], |r| Ok((r.get(0)?, r.get(1)?)))?
        .collect()
}
fn discover(db: &Connection, out: &mut impl Write) -> Result<(), Box<dyn std::error::Error>> {
    let mut stmt = db.prepare("SELECT c.ROWID,coalesce(c.display_name,''),c.chat_identifier,(SELECT count(*) FROM chat_message_join j WHERE j.chat_id=c.ROWID),(SELECT min(m.date) FROM chat_message_join j JOIN message m ON m.ROWID=j.message_id WHERE j.chat_id=c.ROWID),(SELECT max(m.date) FROM chat_message_join j JOIN message m ON m.ROWID=j.message_id WHERE j.chat_id=c.ROWID) FROM chat c WHERE (SELECT count(*) FROM chat_handle_join h WHERE h.chat_id=c.ROWID)>=2")?;
    let hs = handles(db)?;
    for row in stmt.query_map([], |r| {
        Ok((
            r.get::<_, i32>(0)?,
            r.get::<_, String>(1)?,
            r.get::<_, String>(2)?,
            r.get::<_, i64>(3)?,
            r.get::<_, Option<i64>>(4)?,
            r.get::<_, Option<i64>>(5)?,
        ))
    })? {
        let (id, name, identifier, count, start, end) = row?;
        let members: Vec<String> = db
            .prepare("SELECT handle_id FROM chat_handle_join WHERE chat_id=?")?
            .query_map([id], |r| r.get::<_, i32>(0))?
            .filter_map(|r| r.ok().and_then(|n| hs.get(&n).cloned()))
            .collect();
        emit(
            out,
            json!({"schema_version":1,"record":"chat","id":id,"name":name,"identifier":identifier,"members":members,"messages":count,"start":start.map(timestamp),"end":end.map(timestamp)}),
        )?;
    }
    Ok(())
}
fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        return Err("Usage: gc-importer discover|export PATH [CHAT_IDS_COMMA_SEPARATED]".into());
    }
    let db = get_connection(Path::new(&args[2]))?;
    let mut out = BufWriter::new(io::stdout().lock());
    if args[1] == "discover" {
        return discover(&db, &mut out);
    }
    if args[1] != "export" || args.len() < 4 {
        return Err("Export requires selected chat IDs".into());
    }
    let selected: BTreeSet<i32> = args[3]
        .split(',')
        .map(str::parse)
        .collect::<Result<_, _>>()?;
    if selected.is_empty() {
        return Err("Select at least one chat".into());
    }
    let caps = Capabilities::determine(&db)?;
    let hs = handles(&db)?;
    let mut context = QueryContext::default();
    context.set_selected_chat_ids(selected);
    let mut stmt = Message::stream_rows(&db, &caps, &context)?;
    for item in Message::rows(&mut stmt, [])? {
        let mut m = match item {
            Ok(m) => m,
            Err(e) => {
                emit(
                    &mut out,
                    json!({"schema_version":1,"record":"diagnostic","error":e.to_string()}),
                )?;
                continue;
            }
        };
        let person = if m.is_from_me {
            "me".to_string()
        } else {
            m.handle_id
                .and_then(|id| hs.get(&id).cloned())
                .unwrap_or_else(|| "unknown".to_string())
        };
        match m.parse_body(&db) {
            Ok(body) => m.apply_body(body),
            Err(e) => {
                if m.attributed_body(&db).is_some() {
                    emit(
                        &mut out,
                        json!({"schema_version":1,"record":"diagnostic","id":m.guid,"error":e.to_string()}),
                    )?;
                }
            }
        }
        if let Variant::Tapback(part, action, tapback) = m.variant() {
            let kind = match tapback {
                Tapback::Loved => "heart".to_string(),
                Tapback::Liked => "like".to_string(),
                Tapback::Disliked => "dislike".to_string(),
                Tapback::Laughed => "laugh".to_string(),
                Tapback::Emphasized => "emphasize".to_string(),
                Tapback::Questioned => "question".to_string(),
                Tapback::Emoji(e) => e.unwrap_or("unknown emoji").to_string(),
                Tapback::Sticker => "sticker".to_string(),
            };
            emit(
                &mut out,
                json!({"schema_version":1,"record":"reaction","id":m.guid,"source_id":m.rowid,"chat_id":m.chat_id,
                "person":person,"ts":timestamp(m.date),"target":m.clean_associated_guid().map(|(_,guid)|guid),"part":part,
                "type":kind,"action":if action==TapbackAction::Removed {"remove"} else {"add"}}),
            )?;
            continue;
        }
        let announcement = m.get_announcement().map(|a| format!("{a:?}"));
        let kind = if announcement.is_some() || m.item_type != 0 {
            "system"
        } else {
            "message"
        };
        let text = m
            .text
            .clone()
            .unwrap_or_else(|| announcement.clone().unwrap_or_default());
        let parts: Vec<Value>=m.components.iter().enumerate().map(|(i,part)|match part {
            BubbleComponent::Run(ranges)=>json!({"index":i,"kind":"run","ranges":ranges.iter().map(|r|json!({"start":r.start,"end":r.end,
                "text":text.get(r.start..r.end).unwrap_or(""),"effects":format!("{:?}",r.effects),"attachment":r.attachment.as_ref().map(|a|format!("{a:?}"))})).collect::<Vec<_>>() }),
            BubbleComponent::App=>json!({"index":i,"kind":"app"}),BubbleComponent::Retracted=>json!({"index":i,"kind":"retracted"})
        }).collect();
        let edits:Vec<Value>=m.edited_parts.as_ref().map(|e|e.parts.iter().enumerate().map(|(i,p)|json!({"part":i,"status":format!("{:?}",p.status),
            "history":p.edit_history.iter().map(|h|json!({"ts":timestamp(h.date),"text":h.text,"guid":h.guid})).collect::<Vec<_>>() })).collect()).unwrap_or_default();
        let transcripts: HashMap<String, String> = m
            .components
            .iter()
            .filter_map(|component| match component {
                BubbleComponent::Run(ranges) => Some(ranges),
                _ => None,
            })
            .flatten()
            .filter_map(|range| range.attachment.as_ref())
            .filter_map(|a| a.guid.as_ref().zip(a.transcription.as_ref()))
            .map(|(guid, text)| (guid.clone(), text.clone()))
            .collect();
        let attachments:Vec<Value>=Attachment::from_message(&db,&m,&caps)?.into_iter().map(|a|json!({"id":a.guid.clone().unwrap_or_else(||format!("attachment-{}",a.rowid)),
            "path":a.filename,"name":a.transfer_name,"mime":a.mime_type,"bytes":a.total_bytes,"sticker":a.is_sticker,"transcript":a.guid.as_ref().and_then(|guid|transcripts.get(guid))})).collect();
        let (payload_xml, payload_binary_b64) = match m.payload_data(&db) {
            Some(payload) => match encode_payload(&payload) {
                Ok(encoded) => encoded,
                Err(error) => {
                    emit(
                        &mut out,
                        json!({"schema_version":1,"record":"diagnostic",
                        "id":m.guid,"phase":"rich message metadata","error":error.to_string()}),
                    )?;
                    (None, None)
                }
            },
            None => (None, None),
        };
        emit(
            &mut out,
            json!({"schema_version":1,"record":"message","id":m.guid,"source_id":m.rowid,"chat_id":m.chat_id,
            "person":person,"person_name":if person=="me" {Some("You")} else {None},"ts":timestamp(m.date),"text":text,"kind":kind,
            "reply_to":m.thread_originator_guid,"reply_part":m.thread_originator_part,"parts":parts,"edits":edits,"attachments":attachments,
            "announcement":announcement,"variant":format!("{:?}",m.variant()),"service":m.service,"subject":m.subject,
            "date_read":m.date_read,"date_delivered":m.date_delivered,"effect":m.expressive_send_style_id,"payload_xml":payload_xml,"payload_binary_b64":payload_binary_b64}),
        )?;
    }
    out.flush()?;
    Ok(())
}
fn main() {
    if let Err(e) = run() {
        eprintln!("{e}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn keyed_archive_uids_round_trip_without_partial_xml() {
        let mut values = plist::Dictionary::new();
        values.insert("root".into(), plist::Value::Uid(plist::Uid::new(1)));
        values.insert(
            "url".into(),
            plist::Value::String("https://example.invalid/fixture".into()),
        );
        let original = plist::Value::Dictionary(values);
        let (xml, binary) = encode_payload(&original).unwrap();
        assert!(xml.is_none());
        let bytes = STANDARD.decode(binary.unwrap()).unwrap();
        let restored = plist::Value::from_reader(std::io::Cursor::new(bytes)).unwrap();
        assert_eq!(original, restored);
    }

    #[test]
    fn ordinary_payload_xml_is_complete() {
        let original = plist::Value::String("Fictional metadata".into());
        let (xml, binary) = encode_payload(&original).unwrap();
        assert!(binary.is_none());
        let restored = plist::Value::from_reader_xml(xml.unwrap().as_bytes()).unwrap();
        assert_eq!(original, restored);
    }

    #[test]
    fn supports_old_and_new_apple_epochs() {
        assert_eq!(timestamp(600000000), 1578307200.0);
        assert_eq!(timestamp(600000000000000000), 1578307200.0);
    }
}
