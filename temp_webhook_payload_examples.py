first_opening = {
	"event":"unique_opened",
  "email": "example@domain.com",
  "id": "xxxxx",
  "date": "2020-10-09 00:00:00",
  "ts":1604933619,
  "message-id": "201798300811.5787683@relay.domain.com",
  "ts_event": 1604933654,
  "subject": "My first Transactional",
	"X-Mailin-custom": "some_custom_header",
  "sending_ip": "xxx.xxx.xxx.xxx",
  "template_id": 22,
  "tags": ["transac_messages"],
  "user_agent": "Mozilla/5.0 (Windows NT 5.1; rv:11.0) Gecko Firefox/11.0 (via ggpht.com GoogleImageProxy)",
 	"device_used": "DESKTOP",
  "mirror_link": "https://app-smtp.brevo.com/log/preview/1a2000f4-4e33-23aa-ab68-900dxxx9152c",
  "contact_id": 8,
  "ts_epoch": 1604933623
}

opened = {
	"event":"opened",
  "email": "example@domain.com",
  "id": "xxxxx",
  "date": "2020-10-09 00:00:00",
  "ts":1604933619,
  "message-id": "201798300811.5787683@relay.domain.com",
  "ts_event": 1604933654,
  "subject": "My first Transactional",
	"X-Mailin-custom": "some_custom_header",
  "sending_ip": "xxx.xxx.xxx.xxx",
  "template_id": 22,
  "user_agent": "Mozilla/5.0 (Windows NT 5.1; rv:11.0) Gecko Firefox/11.0 (via ggpht.com GoogleImageProxy)",
 	"device_used": "DESKTOP",
  "mirror_link": "https://app-smtp.brevo.com/log/preview/1a2000f4-4e33-23aa-ab68-900dxxx9152c",
  "contact_id": 8,
  "tags": ["transac_messages"],
  "ts_epoch": 1604933623
}

delivered= {
	"event":"delivered",
  "email": "example@domain.com",
  "id": "xxxxx",
  "date": "2020-10-09 00:00:00",
  "ts":1604933619,
  "message-id": "201798300811.5787683@relay.domain.com",
  "ts_event": 1604933654,
  "subject": "My first Transactional",
	"X-Mailin-custom": "some_custom_header",
  "sending_ip": "xxx.xxx.xxx.xxx",
  "template_id": 22,
  "tags": ["transac_messages"],
}

sent = {
	"event":"request",
  "email": "example@domain.com",
  "id": "xxxxx",
  "date": "2020-10-09 00:00:00",
  "ts":1604933619,
  "message-id": "201798300811.5787683@relay.domain.com",
  "ts_event": 1604933654,
  "subject": "My first Transactional",
  "X-Mailin-custom": "some_custom_header",
  "sending_ip": "xxx.xxx.xxx.xxx",
  "ts_epoch": 1604933654,
  "template_id": 22,
  "mirror_link": "https://app-smtp.brevo.com/log/preview/1a2000f4-4e33-23aa-ab68-900dxxx9152c",
  "contact_id": 8,
  "tags": ["transac_messages"]
}

spam = {
	"event":"spam",
  "email": "example@domain.com",
  "id": "xxxxx",
  "date": "2020-10-09 00:00:00",
  "ts":1604933619,
  "message-id": "201798300811.5787683@relay.domain.com",
  "ts_event": 1604933654,
	"X-Mailin-custom": "some_custom_header",
  "tags": ["transac_messages"],
}


invalid_email = {
	"event":"invalid_email",
  "email": "example@domain.com",
  "id": "xxxxx",
  "date": "2020-10-09 00:00:00",
  "ts":1604933619,
  "message-id": "201798300811.5787683@relay.domain.com",
  "ts_event": 1604933654,
  "subject": "My first Transactional",
	"X-Mailin-custom": "some_custom_header",
  "template_id": 22,
  "tags": ["transac_messages"],
  "ts_epoch": 1604933623
}

invalid_email = {
	"event":"invalid_email",
  "email": "example@domain.com",
  "id": xxxxx,
  "date": "2020-10-09 00:00:00",
  "ts":1604933619,
  "message-id": "201798300811.5787683@relay.domain.com",
  "ts_event": 1604933654,
  "subject": "My first Transactional",
	"X-Mailin-custom": "some_custom_header",
  "template_id": 22,
  "tags": ["transac_messages"],
  "ts_epoch": 1604933623
}

soft_bounce = {
	"event":"soft_bounce",
  "email": "example@domain.com",
  "id": "xxxxx",
  "date": "2020-10-09 00:00:00",
  "ts":1604933619,
  "message-id": "201798300811.5787683@relay.domain.com",
  "ts_event": 1604933654,
  "subject": "My first Transactional",
	"X-Mailin-custom": "some_custom_header",
  "sending_ip": "xxx.xxx.xxx.xxx",
  "template_id": 22,
  "tags": ["transac_messages"],
  "reason": "server is down"
}

hard_bounce = {
	"event":"hard_bounce",
  "email": "example@domain.com",
  "id": "xxxxx",
  "date": "2020-10-09 00:00:00",
  "ts":1604933619,
  "message-id": "201798300811.5787683@relay.domain.com",
  "ts_event": 1604933654,
  "subject": "My first Transactional",
	"X-Mailin-custom": "some_custom_header",
  "sending_ip": "xxx.xxx.xxx.xxx",
  "template_id": 22,
  "tags": ["transac_messages"],
  "reason": "server is down",
  "ts_epoch":1604933653 
}

blocked = {
	"event":"blocked",
  "email": "example@domain.com",
  "id": "xxxxx",
  "date": "2020-10-09 00:00:00",
  "ts":1604933619,
  "message-id": "201798300811.5787683@relay.domain.com",
  "ts_event": 1604933654,
  "subject": "My first Transactional",
	"X-Mailin-custom": "some_custom_header",
  "template_id": 22,
  "tags": ["transac_messages"],
  "ts_epoch": 1604933623
}

