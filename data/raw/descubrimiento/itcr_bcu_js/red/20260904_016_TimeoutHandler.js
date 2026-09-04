/**
 * Mecanismo Generico para invocar con setTimeout, setInterval
 */
if (!window.TimeoutHelper) {
	window.TimeoutHelper = {
		tss : {},
		gen : 0,
		
		/**
		 * Public
		 */
		setTimeout : function(fun, millis)
		{
			this.gen ++;
			var tout = window.setTimeout('window.TimeoutHelper.timeOut(\'' + this.gen + '\')', millis);
			this.tss[''+this.gen] = { handler: fun, tout: tout};
			return this.gen;
		},
		
		clearTimeout : function(gen)
		{
			var data = this.tss[gen];
			if (data) {
				window.clearTimeout(data.tout);
				this.cleanTss(gen);
			}
		},
		
		/**
		 * Private
		 */
		timeOut : function(ts) 
		{
			var data = this.tss[ts];
			if (data) { //Fail silently if there is no function associated with the timeoutId (probably clearTimeout was called in a border condition)
				var fun = data.handler;
				this.cleanTss(ts);
				fun();
			}
		},
		
		cleanTss : function(ts)
		{
			delete this.tss[ts];
		}
	};
}

