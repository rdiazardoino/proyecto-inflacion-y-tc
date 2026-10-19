

//http://developer.apple.com/internet/webcontent/xmlhttpreq.html

if (!XMLHttpRequest) {

	try {
		var XMLHttpRequest = function() {
			return new ActiveXObject("Microsoft.XMLHTTP");
		}
	} catch(e) {};
}


var HTTPRequest = {};
HTTPRequest.msxmlNames = [ "MSXML2.XMLHTTP.5.0", "MSXML2.XMLHTTP.4.0", "MSXML2.XMLHTTP.3.0", "MSXML2.XMLHTTP", "Microsoft.XMLHTTP" ];

HTTPRequest.getHTTPRequest =
	function ()
	{
	    // Mozilla XMLHttpRequest
	    try {
		return new XMLHttpRequest();
	    } catch(e) {}

	    // Microsoft MSXML ActiveX
	    for (var i=0;i < HTTPRequest.msxmlNames.length; i++) {
		try {
		    return new ActiveXObject(HTTPRequest.msxmlNames[i]);
		} catch (e) {}
	    }

	    // None found
	    return null;
	}

	
function sendPost(xmlHttpRequest, url, charset, map) {
	xmlHttpRequest.open('POST', url, true);
	var cType = 'application/x-www-form-urlencoded';
	if (charset != null) {
		cType += '; charset=' + charset;
	} 
	xmlHttpRequest.setRequestHeader('Content-Type', cType);
	var params = '';
	for (var p in map) {
		params += p + '=' + encodeURIComponent(map[p]) + '&';
	}
	xmlHttpRequest.send(params);
}


function getXHRListenerSupport(xhr, callback4, callbackNot4) 
{
	var f = 
		function() {
			if (xhr.readyState == 4) {
				if (xhr.status == 200) {
					callback4(true);
				} else {
					callback4(false, xhr.status);
				}
			} else {
				if (callbackNot4) callbackNot4(xhr.readyState);
			}
		};
	return f;
}

/**
 * Simple manager for asynchronous requests using XmlHttpRequest.
 * Uses just one XHR at a given time, avoiding problem with the max. number of concurrent XHRs uses at a time (IE), 
 * and ensuring an order in the execution of requests.
 */
isjs_XHRSimpleManager = 
{
	/** public **/
	
	sendRequest : 
		function(url, rpCB, errCB, timeOut) 
		{
			if (timeOut == void(0)) timeOut = this.TIMEOUT;
			this.queue = this.queue.concat([{url: url, rpCB : rpCB, errCB : errCB, timeOut : timeOut}]);
			this.checkQueue();
		},


	/** private **/

	checkQueue :
		function()
		{
			if (!this.busy) {
				if (this.queue.length > 0) {
					this.busy = true;
					var r = this.queue[this.queue.length - 1];
					this.queue.length = this.queue.length - 1;
					
					var xhr = HTTPRequest.getHTTPRequest();
					this.xhr = xhr;
					this.currentRq = r;
					
					this.tout = window.setTimeout('isjs_XHRSimpleManager.rqTimedOut()', r.timeOut);
					
					xhr.onreadystatechange = getXHRListenerSupport(xhr, function(a, b) { isjs_XHRSimpleManager.rqFinished(a, b);}, null);
					xhr.open("GET", r.url, true);
					if (this.noCache) {
						xhr.setRequestHeader( "If-Modified-Since", "Sat, 1 Jan 2000 00:00:00 GMT" );
					}
					xhr.send(null);
				} 
			}
		},
	
	rqFinished : 
		function(success, status)
		{
			this.clearTout();
			var r = this.currentRq;
			var rsp = null;
			if (this.currentRq) {
				var rsp = this.xhr.responseText;
				this.clearRq();
			}
			this.checkQueue();
			if (r) {
				if (success) {
					r.rpCB(rsp);
				} else {
					r.errCB('Response status is ' + status + '.');
				}
			}
		},
	
	rqTimedOut : 
		function()
		{
			this.tout = null;
			var r = this.currentRq;
			if (this.currentRq) {
				this.clearRq();
			}
			this.checkQueue();
		 	if (r) r.errCB('Request timed out.');
		},

	clearRq :
		function()
		{
			if (this.xhr != null) this.xhr.abort();
			this.currentRq = null;
			this.xhr = null;
			this.busy = false;
		},
	
	clearTout :
		function() 
		{
			if (this.tout != null) {
				 window.clearTimeout(this.tout);
				 this.tout = null;
			}
		},

	/** Members **/ 	
	
	TIMEOUT : 10000,
	
	currentRq : null,
	
	xhr : null,
	
	busy : false,
	
	noCache : true,
	
	tout : null,
	
	queue : []
};
