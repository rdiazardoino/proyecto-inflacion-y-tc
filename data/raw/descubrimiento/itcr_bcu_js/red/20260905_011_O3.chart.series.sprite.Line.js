Ext.define('O3.chart.series.sprite.Line', {
    override: 'Ext.chart.series.sprite.Line',
    constructor: function(){
        var me = this;

        me.self.def.getUpdaters().smooth = me.customSmootho;
        me.callParent(arguments);

    },
    customSmootho: function (attr) { 
        var dataX = attr.dataX,
            dataY = attr.dataY;
        if (attr.smooth && dataX && dataY && dataX.length > 2 && dataY.length > 2) {
            var smoothResult =  Ext.draw.Draw.smooth(dataX, dataY);
            this.smoothX = smoothResult.smoothX;
            this.smoothY = smoothResult.smoothY;
        } else {
            delete this.smoothX;
            delete this.smoothY;
        }
    }
});


Ext.chart.axis.layout.CombineDuplicate.override({
    getCoordFor: function (value, field, idx, items) {
        if (!(items[idx].id in this.labelMap)) {
            var result = this.labelMap[items[idx].id] = idx;
            this.labels.push(value);
            return result;
        }
        return this.labelMap[items[idx].id];
    }
});