

function FlashPortlet(instanceData, resourceURL, id/*, userName, ticket*/) 
{
	this.instanceData = instanceData;
	this.resourceURL = resourceURL;
	this.id = id;
	/*
	this.userName = userName;
	this.ticket = ticket;
	*/
}


function __FlashPortlet_getInstanceData() /*:String*/
{
	return this.instanceData;
}


function __FlashPortlet_setInstanceData(value/*:String*/)
{
	//TODO usar un pool
	//TODO timeout
	var req = HTTPRequest.getHTTPRequest();
	var me = this;
	req.onreadystatechange = function() { me.onSetInstanceDataResponse(req); };
	sendPost(req, this.resourceURL, 'UTF-8', {instanceData:value});
	this.instanceData = value;
}

function __FlashPortlet_sendMessage(type/*:String*/, value/*:String*/)
{
	ClientCommunicationBus.fireEvent(type, value); 
}

function __FlashPortlet_setMessageReceiver(type/*:String*/, fName/*:String*/)
{
	var me = this;
	var f = function(eventName, data) {
		var fapp = getFlexApp(me.id);
		if (fapp == null) {
			alert("flex app not found: " + me.id);
		} else {
			if (typeof(data) == 'undefined') {
				fapp[fName](eventName); //no puedo factorizar fapp[el] debido a un error de seguridad en FF3.0/linux
			} else {
				fapp[fName](eventName, data);
			}
		}
	};
	
	ClientCommunicationBus.addListener(f, type);
}


//function __FlashPortlet_setTitle(value/*:String*/)/*:void*/
//{
//	
//}
//
//

//function __FlashPortlet_getAuthenticatedUserName()/*: String*/
//{
//	return this.userName;
//}


//function __FlashPortlet_getAuthenticationTicket()/*: String*/
//{
//	return this.ticket;
//}


function __FlashPortlet_onSetInstanceDataResponse(httpreq/*:XMLHttpRequest*/) {
	if (httpreq.readyState == 4) {
		var resp = httpreq.responseText;
		var status = httpreq.status;
		var xmlResponse = "<response><status>"+ status +"</status><text>"+ resp +"</text></response>";
		ClientCommunicationBus.fireEvent("instanceDataSaved", xmlResponse);
	}
}

FlashPortlet.prototype.getInstanceData = __FlashPortlet_getInstanceData;

FlashPortlet.prototype.onSetInstanceDataResponse = __FlashPortlet_onSetInstanceDataResponse;

FlashPortlet.prototype.setInstanceData = __FlashPortlet_setInstanceData;

FlashPortlet.prototype.sendMessage = __FlashPortlet_sendMessage;

FlashPortlet.prototype.setMessageReceiver = __FlashPortlet_setMessageReceiver;

//FlashPortlet.prototype.getAuthenticatedUserName = __FlashPortlet_getAuthenticatedUserName;

//FlashPortlet.prototype.getAuthenticationTicket = __FlashPortlet_getAuthenticationTicket;


var ClientCommunicationBus = {

		eventListeners: {},
		
		/**
		 * indexed by their eventName.
		 */
		persistentEvents: {},
			
		addListener: function(callback, eventName) {
			if (! this.eventListeners[eventName]) {
				this.eventListeners[eventName] = [];
			}
			var el = this.eventListeners[eventName]; 
			el[el.length] = callback;
			
			var persistentEvent = this.persistentEvents[eventName];
			if (persistentEvent != null) {
				TimeoutHelper.setTimeout(function() {
					callback(eventName, persistentEvent.data);
				}, 1);
			}
		},

		fireEvent: function(eventName, data) {
			this.persistentEvents[eventName] = {"data": data};
			var els = this.eventListeners[eventName];
			if (typeof(els) == 'undefined') {
				return;
			}
			var el;
			for (var i = 0; i < els.length; i++) {
				el = this.eventListeners[eventName][i]; 
				if (typeof(data) == 'undefined') {
					el(eventName);
				} else {
					el(eventName, data);
				}
			}
		}

	}



function getFlexApp(appName)
{
  if (navigator.appName.indexOf("Microsoft") !=-1)
  {
    return window[appName];
  }
  else
  {
    return document[appName];
  }
}			
