/*

BUG DETECTADO EN LA VERSION 4.2 de ExtJS
No formatea numeros negativos.

https://www.sencha.com/forum/showthread.php?265856-Ext.util.Format.number-and-negative-numbers

*/

Ext.define('O3Ext.util.Format', {
    override: 'Ext.util.Format',
    originalNumberFormatter: Ext.util.Format.number,
    number: function(v, formatString) {
        if (v < 0) {
            //negative number: flip the sign, format then prepend '-' onto output
            return '-' + this.originalNumberFormatter(v * -1, formatString);
        } else {
            //positive number: as you were
            return this.originalNumberFormatter(v, formatString);
        }
    }
});